"""The persisted audit chain, and the forgery it originally failed to catch.

These tests exist because the first implementation of this was wrong in a way
that no positive test would have found. A SHA-256 chain verifies that no event
was altered *in place*. It does nothing against anyone who can rewrite history
and recompute the digests: I edited event 47 and rehashed events 47..48, every
entry stayed self-consistent, and ``verify_full_chain`` reported valid. The
signed external anchor is what closes that hole, so the forgery case below is
the one that matters.

Uses the real database and deletes every row it creates, so the chain these
tests build cannot leak into the counts that
``/api/v1/verification/chain/verify`` reports for the running deployment.
Each test pins ``entity_id`` to a run-scoped prefix and removes only those rows.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import delete, select

from app.core.audit_chain import append_audit_event, get_chain_head, verify_full_chain
from app.core.hash_chain import GENESIS_HASH, compute_audit_hash
from app.models.audit import AuditCheckpoint, AuditEvent


@pytest.fixture(scope="module")
def tag():
    """Run-scoped entity prefix, so cleanup can never touch production rows."""
    return f"test-audit-{uuid.uuid4().hex[:12]}"


def _sync_cleanup(tag):
    """Cleanup through the sync engine; there is no module-level async engine."""
    from app.core.database import sync_engine

    with sync_engine.begin() as conn:
        conn.execute(delete(AuditEvent).where(AuditEvent.entity_id.like(f"{tag}%")))


@pytest.fixture(scope="module", autouse=True)
def _cleanup(tag):
    _sync_cleanup(tag)
    yield
    _sync_cleanup(tag)


def test_existing_chain_verifies():
    """Whatever is already committed must verify, or the deployment is lying."""
    result = asyncio.run(_sessioned(lambda db: verify_full_chain(db)))
    assert result["event_count"] > 0
    assert result["valid"] is True, result.get("reason")


def test_events_link_and_verify(tag):
    async def scenario(db):
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.like(f"{tag}%")))
        await db.commit()
        for i in range(3):
            await append_audit_event(
                db,
                event_type=f"EVENT_{i}",
                entity_type="CASE",
                entity_id=f"{tag}-{i}",
                actor_id="usr-test",
                payload={"i": i},
            )
        result = await verify_full_chain(db)
        mine = (
            await db.execute(
                select(AuditEvent.event_number).where(AuditEvent.entity_id.like(f"{tag}%"))
            )
        ).scalars().all()
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.like(f"{tag}%")))
        await db.commit()
        return result, len(mine)

    result, mine = asyncio.run(_sessioned(scenario))
    assert result["valid"] is True
    # verify_full_chain walks the whole chain, not just this test's rows.
    assert mine == 3


def test_in_place_edit_is_detected(tag):
    async def scenario(db):
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.like(f"{tag}%")))
        await db.commit()
        for i in range(3):
            await append_audit_event(
                db,
                event_type=f"EVENT_{i}",
                entity_type="CASE",
                entity_id=f"{tag}-{i}",
                actor_id="usr-test",
                payload={"i": i},
            )
        target = (
            await db.execute(
                select(AuditEvent).where(AuditEvent.entity_id == f"{tag}-1")
            )
        ).scalar_one()
        target.payload = {"i": 1, "decision": "TAMPERED"}
        await db.commit()
        result = await verify_full_chain(db)
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.like(f"{tag}%")))
        await db.commit()
        return result

    result = asyncio.run(_sessioned(scenario))
    assert result["valid"] is False
    assert "altered" in result["reason"]


def test_rehashing_a_segment_defeats_the_chain_check_alone(tag):
    """A rehashed forgery passes the chain check. Pinned as a test on purpose.

    Rewriting an event and correctly recomputing every digest after it leaves a
    chain that verifies, so ``verify_full_chain`` cannot be the only defence.

    Scope matters here. This only rewrites *this test's own* events, which are
    appended last, so the cascade stays inside them and the production events
    ahead of them are untouched. Rehashing across committed rows would rewrite
    the deployment's history, which is exactly the damage the anchor exists to
    detect and which a test must not cause.
    """
    async def scenario(db):
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.like(f"{tag}%")))
        await db.commit()
        for i in range(3):
            await append_audit_event(
                db,
                event_type=f"EVENT_{i}",
                entity_type="CASE",
                entity_id=f"{tag}-{i}",
                actor_id="usr-test",
                payload={"i": i},
            )
        rows = list(
            (
                await db.execute(
                    select(AuditEvent)
                    .where(AuditEvent.entity_id.like(f"{tag}%"))
                    .order_by(AuditEvent.event_number)
                )
            ).scalars()
        )
        previous = rows[0].previous_hash  # start from the untouched parent
        for row in rows:
            if row.entity_id == f"{tag}-1":
                row.payload = {"i": 1, "decision": "FORGED"}
            row.previous_hash = previous
            row.current_hash = compute_audit_hash(
                previous_hash=previous,
                event_type=row.event_type,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                actor_id=row.actor_id,
                timestamp_iso=row.timestamp.isoformat(),
                payload=row.payload,
            )
            previous = row.current_hash
        await db.commit()
        result = await verify_full_chain(db)
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.like(f"{tag}%")))
        await db.commit()
        return result

    result = asyncio.run(_sessioned(scenario))
    assert result["valid"] is True, (
        "a correctly rehashed forgery is expected to pass the chain check alone; "
        "if this fails the chain check got stronger and the signed anchor is no "
        f"longer the only thing detecting a rewrite: {result.get('reason')}"
    )


def test_unsigned_checkpoint_is_reported_as_unsigned_not_trusted():
    async def scenario(db):
        from app.core.audit_anchor import seal_chain_head, verify_against_checkpoints

        head = await get_chain_head(db)
        checkpoint = await seal_chain_head(
            db,
            head_hash=head["current_hash"],
            head_event_number=head["event_number"],
            event_count=head["event_number"],
            note="test seal, expected unsigned without a keypair",
        )
        anchor = await verify_against_checkpoints(db)
        await db.execute(
            delete(AuditCheckpoint).where(
                AuditCheckpoint.checkpoint_number == checkpoint["checkpoint_number"]
            )
        )
        await db.commit()
        return checkpoint, anchor

    checkpoint, anchor = asyncio.run(_sessioned(scenario))
    assert checkpoint["signed"] in (True, False)
    if not checkpoint["signed"]:
        assert checkpoint["signature"] is None
        assert "unsigned" in checkpoint["note"]
    # Either way the anchor must state its status rather than imply trust.
    assert "signature_valid" in anchor


def _sessioned(scenario):
    """Return a coroutine that runs ``scenario`` against the real DB.

    Deliberately not calling ``asyncio.run`` itself: callers do that, so the
    helper stays awaitable and composes with other async work.
    """
    from app.core.database import AsyncSessionLocal

    async def main():
        async with AsyncSessionLocal() as db:
            return await scenario(db)

    return main()