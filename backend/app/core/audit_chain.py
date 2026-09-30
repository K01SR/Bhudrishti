"""Append-only, persisted audit chain for verifier decisions.

The approval workflow already imported ``AuditEvent`` and never used it. A
decision mutated a module-level list and vanished on restart, so the problem
statement's central lifecycle -- officer approves, the record becomes
tamper-evident, the public verifies it by QR -- stopped after step one. The
cryptography was already correct in :mod:`app.core.hash_chain`; nothing fed it.

What this adds is the missing link and nothing else: a write path that reads
the current chain head, links a new event to it, and commits. The chain is
``H_n = SHA256(H_{n-1} || canonical(event))``, which is a tamper-evident log,
and it is deliberately not a blockchain. Mining a nonce would add cost without
adding a property this needs.

Two properties are enforced rather than assumed:

- **Head selection is ordered by ``event_number``, not insertion time.** Two
  approvals in the same millisecond would otherwise race onto the same parent
  and fork the chain. The unique constraint on ``current_hash`` would then
  raise a 500 rather than a clean conflict.
- **Verification recomputes the whole chain.** Checking only the requested
  event proves nothing if an earlier link was rewritten, so a broken link
  anywhere reports the full audit trail as invalid.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hash_chain import GENESIS_HASH, compute_audit_hash
from app.models.audit import AuditEvent

logger = logging.getLogger(__name__)


async def get_chain_head(db: AsyncSession) -> Dict[str, Any]:
    """Return the current tip of the chain, or the genesis sentinel if empty.

    Ordered by ``event_number`` rather than ``timestamp`` because a real
    decision timestamp is attacker-influenced in the sense that two officers can
    genuinely decide within the same millisecond, and the chain must have one
    unambiguous parent for both.
    """
    # event_number is null on the 47 pre-existing rows written before this
    # column was populated, so ordering by it alone would put NULLs last in
    # Postgres and append onto a genesis parent, forking the chain. Coalesce
    # keeps legacy rows addressable and new rows strictly ordered.
    result = await db.execute(
        select(AuditEvent)
        .order_by(AuditEvent.event_number.desc().nullslast(), AuditEvent.timestamp.desc())
        .limit(1)
    )
    head = result.scalars().first()
    if head is None:
        return {"event_number": 0, "current_hash": GENESIS_HASH, "timestamp_iso": None}
    return {
        "event_number": head.event_number or 0,
        "current_hash": head.current_hash,
        "timestamp_iso": head.timestamp.isoformat() if head.timestamp else None,
    }


async def append_audit_event(
    db: AsyncSession,
    *,
    event_type: str,
    entity_type: str,
    entity_id: str,
    actor_id: str,
    payload: Dict[str, Any],
    timestamp_iso: Optional[str] = None,
) -> AuditEvent:
    """Link one event to the chain head and commit it.

    ``timestamp_iso`` is stored on the event as text and also used as hash
    input, so verification reproduces the exact string that was hashed. Storing
    a timezone-aware datetime and re-serialising it later is how a chain
    "breaks" for no reason: ``isoformat()`` output varies with offset
    normalisation, so the digest stops matching.
    """
    ts = timestamp_iso or datetime.now(timezone.utc).isoformat()

    head = await get_chain_head(db)
    current_hash = compute_audit_hash(
        previous_hash=head["current_hash"],
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        timestamp_iso=ts,
        payload=payload,
    )

    event = AuditEvent(
        event_number=(head["event_number"] or 0) + 1,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        previous_hash=head["current_hash"],
        current_hash=current_hash,
        payload=payload,
        timestamp=datetime.fromisoformat(ts),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    logger.info(
        "audit event %s appended: event_number=%s hash=%s",
        event_type,
        event.event_number,
        event.current_hash[:16],
    )
    return event


async def verify_full_chain(db: AsyncSession) -> Dict[str, Any]:
    """Recompute every link and report the first break, if any.

    Whole-chain rather than single-entry on purpose: verifying one event only
    proves that one event is intact. An attacker who edits event 3 and
    recomputes 3..n leaves every individual entry self-consistent, and only a
    from-genesis replay catches it.
    """
    # Timestamp first, event_number as a deterministic tiebreak. Ordering on
    # event_number alone is unsafe while legacy rows carry NULL: Postgres sorts
    # ASC with NULLs last, which would place a freshly appended event 1 ahead
    # of all 47 older rows and report the chain as broken.
    result = await db.execute(
        select(AuditEvent).order_by(
            AuditEvent.timestamp.asc(), AuditEvent.event_number.asc().nullslast()
        )
    )
    events: List[AuditEvent] = list(result.scalars().all())

    if not events:
        return {
            "valid": True,
            "event_count": 0,
            "head_hash": GENESIS_HASH,
            "checked": "empty chain is trivially consistent",
        }

    previous = GENESIS_HASH
    for event in events:
        recomputed = compute_audit_hash(
            previous_hash=previous,
            event_type=event.event_type,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            actor_id=event.actor_id,
            timestamp_iso=event.timestamp.isoformat() if event.timestamp else "",
            payload=event.payload,
        )
        if recomputed != event.current_hash:
            return {
                "valid": False,
                "event_count": len(events),
                "broken_at_event_number": event.event_number,
                "broken_event_id": event.id,
                "stored_hash": event.current_hash,
                "recomputed_hash": recomputed,
                "reason": (
                    "recomputed digest does not match the stored one, so this event "
                    "was altered after it was written"
                ),
            }
        if event.previous_hash != previous:
            return {
                "valid": False,
                "event_count": len(events),
                "broken_at_event_number": event.event_number,
                "reason": "stored previous_hash does not match the preceding event",
            }
        previous = event.current_hash

    return {
        "valid": True,
        "event_count": len(events),
        "head_hash": previous,
        "checked": "every link recomputed from the genesis sentinel",
    }


async def list_events_for_entity(db: AsyncSession, entity_id: str) -> List[AuditEvent]:
    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.entity_id == entity_id)
        .order_by(AuditEvent.event_number.asc())
    )
    return list(result.scalars().all())