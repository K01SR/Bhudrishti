import hashlib
from typing import Any, Dict, Optional
from app.core.crypto import canonicalize_json

GENESIS_HASH = "0" * 64


def compute_audit_hash(
    previous_hash: Optional[str],
    event_type: str,
    entity_type: str,
    entity_id: str,
    actor_id: str,
    timestamp_iso: str,
    payload: Dict[str, Any],
) -> str:
    """
    Computes deterministic SHA-256 hash for audit event in the tamper-evident hash chain:
    H_n = SHA256(H_{n-1} || canonical(event_data))
    """
    prev = previous_hash if previous_hash else GENESIS_HASH
    event_dict = {
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "actor_id": actor_id,
        "timestamp": timestamp_iso,
        "payload": payload,
    }
    canonical_event = canonicalize_json(event_dict)
    combined = f"{prev}:{canonical_event}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def verify_hash_chain_entry(
    previous_hash: str,
    current_hash: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    actor_id: str,
    timestamp_iso: str,
    payload: Dict[str, Any],
) -> bool:
    """Verifies that current_hash correctly chains from previous_hash."""
    expected = compute_audit_hash(
        previous_hash=previous_hash,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        timestamp_iso=timestamp_iso,
        payload=payload,
    )
    return expected == current_hash
