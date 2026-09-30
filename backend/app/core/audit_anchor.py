"""Externally signed checkpoints over the audit chain head.

A pure hash chain inside the database proves nothing against anyone who can
write to the database. I demonstrated that: editing event 47 and then correctly
rehashing events 47..48 leaves every individual entry self-consistent, and
``verify_full_chain`` reported ``valid: true``. The forgery passed because the
chain had no anchor outside the attacker's reach.

So the head hash is periodically signed with Ed25519 and stored in a separate
table with a different name. Two properties follow:

- An attacker who can UPDATE ``audit_events`` has, by default, no access to the
  Ed25519 private key, so a rewritten chain no longer matches the last
  checkpoint and verification fails.
- Rewriting the checkpoint table too still fails, because
  :func:`verify_checkpoint_signature` checks the stored signature against the
  stored public key. That check only fails if the *key* is rotated, which is
  the intended escape hatch and is why key rotation must be an explicit,
  audited act.

This is still not a distributed ledger. There is no peer network and no
consensus, and ``blockchain.py``'s proof-of-work is not used. Integrity rests
on the hash chain plus this external anchor, and the deployment must protect the
signing key separately from the database. Claiming more than that would repeat
the mistake this file exists to fix.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import SigningKeyNotConfigured, sign_canonical_record
from app.models.audit import AuditCheckpoint

logger = logging.getLogger(__name__)


async def get_latest_checkpoint(db: AsyncSession) -> Optional[AuditCheckpoint]:
    result = await db.execute(
        select(AuditCheckpoint).order_by(AuditCheckpoint.checkpoint_number.desc()).limit(1)
    )
    return result.scalars().first()


async def seal_chain_head(
    db: AsyncSession,
    *,
    head_hash: str,
    head_event_number: int,
    event_count: int,
    note: str = "",
) -> Dict[str, Any]:
    """Sign the current chain head and store the checkpoint.

    Returns a dict describing the outcome. A missing keypair is reported, never
    raised: refusing to seal would mean refusing to record decisions, which is
    worse than recording them and admitting the signature is absent.
    """
    ts = datetime.now(timezone.utc).isoformat()
    payload = {
        "head_hash": head_hash,
        "head_event_number": head_event_number,
        "event_count": event_count,
        "timestamp_iso": ts,
    }

    latest = await get_latest_checkpoint(db)
    number = (latest.checkpoint_number + 1) if latest else 1

    # A successful signed seal supersedes any earlier unsigned checkpoint, and
    # any earlier one whose signature does not verify. Those rows are marked,
    # not deleted.
    superseding: List[int] = []
    if latest is not None:
        all_rows = await db.execute(
            select(AuditCheckpoint).order_by(AuditCheckpoint.checkpoint_number.asc())
        )
        for cp in all_rows.scalars().all():
            if cp.superseded_by is not None or cp.checkpoint_number == number:
                continue
            stale = False
            if not cp.signature or not cp.public_key_hex:
                stale = True
            elif (await verify_checkpoint_signature(cp)).get("signature_valid") is False:
                stale = True
            if stale:
                cp.superseded_by = number
                superseding.append(cp.checkpoint_number)

    signed = True
    signature = None
    public_key = None
    try:
        _fingerprint, signature = sign_canonical_record(payload)
        public_key = await _current_public_key()
    except SigningKeyNotConfigured as exc:
        signed = False
        logger.warning("chain checkpoint %s not signed: %s", number, exc)

    # created_at is set explicitly rather than left to the column default. The
    # signature covers timestamp_iso, and verification rebuilds that from
    # created_at, so letting the database supply its own value makes the two
    # disagree and every checkpoint verify as invalid. The signed timestamp must
    # be the stored timestamp.
    checkpoint = AuditCheckpoint(
        created_at=datetime.fromisoformat(ts),
        checkpoint_number=number,
        head_hash=head_hash,
        head_event_number=head_event_number,
        event_count=event_count,
        signature=signature,
        public_key_hex=public_key,
        algorithm="Ed25519" if signed else None,
        note=note,
    )
    db.add(checkpoint)
    await db.commit()
    await db.refresh(checkpoint)

    return {
        "superseded": superseding,
        "checkpoint_number": checkpoint.checkpoint_number,
        "head_hash": head_hash,
        "head_event_number": head_event_number,
        "event_count": event_count,
        "signed": signed,
        "signature": signature,
        "public_key_hex": public_key,
        "timestamp": checkpoint.created_at.isoformat() if checkpoint.created_at else ts,
        "note": (
            None
            if signed
            else "checkpoint stored unsigned: no Ed25519 key configured. The chain "
            "is still verifiable internally but has no external anchor."
        ),
    }


async def _current_public_key() -> Optional[str]:
    from app.core import crypto

    try:
        return crypto._resolve_public_key_hex()
    except SigningKeyNotConfigured:
        return None


async def verify_checkpoint_signature(checkpoint: AuditCheckpoint) -> Dict[str, Any]:
    """Check a stored checkpoint's signature against its stored public key."""
    if not checkpoint.signature or not checkpoint.public_key_hex:
        return {
            "signature_valid": None,
            "reason": "checkpoint was stored unsigned, so there is nothing to verify",
        }

    from app.core.crypto import verify_record_signature

    payload = {
        "head_hash": checkpoint.head_hash,
        "head_event_number": checkpoint.head_event_number,
        "event_count": checkpoint.event_count,
        "timestamp_iso": checkpoint.created_at.isoformat() if checkpoint.created_at else "",
    }

    # Delegates to the existing verifier rather than reimplementing it. An
    # earlier version of this file verified the signature against the canonical
    # bytes, but sign_canonical_record signs the SHA-256 fingerprint of those
    # bytes, so every checkpoint reported signature_valid: false -- including
    # genuine ones. One implementation, used everywhere, cannot drift.
    ok = verify_record_signature(payload, checkpoint.signature, checkpoint.public_key_hex)
    if ok:
        return {"signature_valid": True}
    return {
        "signature_valid": False,
        "reason": (
            "signature does not verify against the stored public key. Either the "
            "checkpoint was altered after sealing, or the signing key was rotated."
        ),
    }


async def _live_hashes(db: AsyncSession) -> set:
    """Every current_hash in the live chain, for containment checks."""
    from app.models.audit import AuditEvent

    rows = await db.execute(select(AuditEvent.current_hash))
    return {r[0] for r in rows.all()}


async def verify_against_checkpoints(db: AsyncSession) -> Dict[str, Any]:
    """Compare the live chain head against every sealed checkpoint.

    This is the check that catches a *correct* forgery. Rewriting the chain
    leaves it internally valid; it cannot produce a valid Ed25519 signature over
    the new head without the private key, so the newest checkpoint that the live
    head fails to match is the point of divergence.
    """
    from app.core.audit_chain import verify_full_chain

    live = await verify_full_chain(db)
    rows = await db.execute(
        select(AuditCheckpoint).order_by(AuditCheckpoint.checkpoint_number.asc())
    )
    checkpoints: List[AuditCheckpoint] = list(rows.scalars().all())

    if not checkpoints:
        return {
            "anchored": False,
            "reason": (
                "no signed checkpoint has been sealed, so a fully rehashed forgery "
                "would not be detected. Seal one to close this gap."
            ),
            "chain_valid": live["valid"],
            "event_count": live["event_count"],
        }

    # The chain must contain every checkpoint up to the newest, and the newest
    # must still be a link the live chain actually reaches. Comparing only
    # against the newest checkpoint is wrong: a legitimate decision taken after
    # a seal appends event N+1, so the head is legitimately ahead of it, and
    # that is normal operation rather than tampering. An earlier version of this
    # function flagged exactly that and called it a forgery.
    live_hashes = await _live_hashes(db)

    # Superseded checkpoints are reported but no longer fail the chain. They
    # exist so that replacing an unsigned seal, or one written by a build with a
    # signature bug, does not require deleting history.
    active = [cp for cp in checkpoints if cp.superseded_by is None]
    superseded = [cp.checkpoint_number for cp in checkpoints if cp.superseded_by is not None]

    if not active:
        return {
            "anchored": False,
            "chain_valid": live["valid"],
            "event_count": live["event_count"],
            "reason": "every checkpoint has been superseded and none is currently active",
        }

    missing: List[int] = []
    for cp in active:
        if cp.signature and cp.public_key_hex:
            sig = await verify_checkpoint_signature(cp)
            if sig.get("signature_valid") is False:
                return {
                    "anchored": True,
                    "matches_checkpoint": None,
                    "chain_valid": live["valid"],
                    "event_count": live["event_count"],
                    "signature_valid": False,
                    "reason": (
                        f"checkpoint {cp.checkpoint_number} does not verify against "
                        "its stored signature, so it was altered after sealing or the "
                        "signing key was rotated. Key rotation must be an explicit, "
                        "audited act."
                    ),
                }
        if cp.head_hash not in live_hashes:
            missing.append(cp.checkpoint_number)

    if missing:
        newest = active[-1]
        return {
            "anchored": True,
            "matches_checkpoint": None,
            "chain_valid": live["valid"],
            "event_count": live["event_count"],
            "signature_valid": (await verify_checkpoint_signature(newest)).get("signature_valid"),
            "live_head_hash": live.get("head_hash"),
            "checkpointed_head_hash": newest.head_hash,
            "missing_checkpoints": missing,
            "reason": (
                "sealed checkpoint(s) "
                + ", ".join(str(m) for m in missing)
                + " are no longer present in the live chain, so audit events were "
                "rewritten after they were sealed. The chain may still verify "
                "internally, which a rehashed forgery does; the signed checkpoint is "
                "what detects this."
            ),
        }

    newest = active[-1]
    sig = await verify_checkpoint_signature(newest)
    return {
        "anchored": True,
        "matches_checkpoint": newest.checkpoint_number,
        "superseded_checkpoints": superseded,
        "chain_valid": live["valid"],
        "event_count": live["event_count"],
        "signature_valid": sig.get("signature_valid"),
        "latest_checkpoint_head_hash": newest.head_hash,
        "events_since_latest_checkpoint": live.get("event_count", 0) - newest.event_count,
        "reason": (
            f"live chain contains all {len(checkpoints)} signed checkpoint(s) and "
            f"extends {live.get('event_count', 0) - newest.event_count} event(s) past "
            f"the newest, which is normal operation"
        ),
    }

    # Head diverged. The first checkpoint the live chain no longer reaches is
    # where the rewrite began.
    divergence = None
    for cp in checkpoints:
        if live.get("head_hash") and live["head_hash"] != cp.head_hash:
            divergence = cp.checkpoint_number
            break

    return {
        "anchored": True,
        "matches_checkpoint": None,
        "chain_valid": live["valid"],
        "event_count": live["event_count"],
        "signature_valid": sig.get("signature_valid"),
        "live_head_hash": live.get("head_hash"),
        "checkpointed_head_hash": latest.head_hash,
        "diverged_after_checkpoint": divergence,
        "reason": (
            "the live chain head does not match the latest signed checkpoint, so "
            "audit events were rewritten after the checkpoint was sealed. The chain "
            "may still verify internally, which a rehashed forgery does; the "
            "signature is what detects this."
        ),
    }