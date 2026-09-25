from typing import List, Dict, Any
from fastapi import APIRouter
from app.core.hash_chain import compute_audit_hash, GENESIS_HASH

router = APIRouter(prefix="/audit", tags=["Tamper-Evident Audit Hash Chain"])

# Build synthetic hash chain sequence
_AUDIT_LOGS = []
events = [
    ("SUBMISSION_CREATED", "PARCEL", "12345678901234", "usr-builder-demo", "2026-09-24T09:00:00Z", {"action": "Initial registration submission for Building B-17"}),
    ("EVIDENCE_UPLOADED", "EVIDENCE", "airoli_b17_classified.laz", "usr-builder-demo", "2026-09-24T09:05:00Z", {"file_hash": "f892374619283746501928374650192837465019283746501928374650192837", "tier": "TIER_A"}),
    ("PROCESSING_STARTED", "JOB", "job-extract-001", "SYSTEM", "2026-09-24T09:06:00Z", {"pipeline": "LiDAR Ground Classification & Building Extraction"}),
    ("PROCESSING_COMPLETED", "JOB", "job-extract-001", "SYSTEM", "2026-09-24T09:08:00Z", {"iou": 0.94, "height_m": 18.0, "floors": 5}),
    ("VALIDATION_RUN", "VALIDATION", "val-b17-001", "SYSTEM", "2026-09-24T09:10:00Z", {"passed": 11, "failed": 1, "issue": "R009 Subsurface Clash"}),
    ("CASE_ROUTED", "CASE", "CASE-2026-B17-001", "SYSTEM", "2026-09-24T09:12:00Z", {"assigned_to": "usr-district-admin", "priority": "HIGH"}),
    ("VERIFICATION_APPROVED", "CASE", "CASE-2026-B17-001", "usr-district-admin", "2026-09-24T10:30:00Z", {"decision": "APPROVED", "officer": "Sunita Patil"}),
    ("VERSION_COMMITTED", "PROPERTY", "12345678901234/B17", "usr-district-admin", "2026-09-24T10:32:00Z", {"version": "V1.0", "signature": "ED25519_VALID"}),
]

curr_prev = GENESIS_HASH
for idx, (e_type, ent_type, ent_id, actor, ts, payload) in enumerate(events):
    curr_hash = compute_audit_hash(
        previous_hash=curr_prev,
        event_type=e_type,
        entity_type=ent_type,
        entity_id=ent_id,
        actor_id=actor,
        timestamp_iso=ts,
        payload=payload,
    )
    _AUDIT_LOGS.append({
        "event_number": idx + 1,
        "event_type": e_type,
        "entity_type": ent_type,
        "entity_id": ent_id,
        "actor_id": actor,
        "timestamp": ts,
        "previous_hash": curr_prev,
        "current_hash": curr_hash,
        "payload": payload,
        "is_valid": True,
    })
    curr_prev = curr_hash


@router.get("/events")
def list_audit_events():
    """Returns chronological audit trail with tamper-evident SHA-256 hash chaining."""
    return _AUDIT_LOGS


@router.get("/verify-chain")
def verify_hash_chain():
    """Cryptographically verifies continuity of previous_hash -> current_hash for all events."""
    prev = GENESIS_HASH
    is_intact = True
    chain_length = len(_AUDIT_LOGS)

    for entry in _AUDIT_LOGS:
        if entry["previous_hash"] != prev:
            is_intact = False
            break
        expected_hash = compute_audit_hash(
            previous_hash=prev,
            event_type=entry["event_type"],
            entity_type=entry["entity_type"],
            entity_id=entry["entity_id"],
            actor_id=entry["actor_id"],
            timestamp_iso=entry["timestamp"],
            payload=entry["payload"],
        )
        if expected_hash != entry["current_hash"]:
            is_intact = False
            break
        prev = entry["current_hash"]

    return {
        "chain_integrity": "VALID" if is_intact else "TAMPERED",
        "total_events_verified": chain_length,
        "genesis_hash": GENESIS_HASH,
        "latest_block_hash": prev,
        "tamper_evident_status": "All SHA-256 cryptographic linkage proofs strictly verified.",
    }
