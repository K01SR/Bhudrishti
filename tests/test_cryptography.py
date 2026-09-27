import pytest
from app.core.crypto import (
    canonicalize_json,
    sha256_hash,
    sign_canonical_record,
    verify_record_signature,
)
from app.core.hash_chain import compute_audit_hash, GENESIS_HASH


def test_canonicalize_json_order_independent():
    dict_a = {"z": 1, "a": 2, "m": {"b": 3, "a": 4}}
    dict_b = {"a": 2, "z": 1, "m": {"a": 4, "b": 3}}
    assert canonicalize_json(dict_a) == canonicalize_json(dict_b)


def test_ed25519_sign_and_verify():
    payload = {
        "parent_ulpin": "12345678901234",
        "structure_id": "B-17",
        "units_count": 21,
        "status": "APPROVED",
    }
    fp, sig = sign_canonical_record(payload)
    assert len(fp) == 64
    assert len(sig) == 128
    assert verify_record_signature(payload, sig) is True

    # Mutated payload must fail verification
    mutated = dict(payload)
    mutated["status"] = "REJECTED"
    assert verify_record_signature(mutated, sig) is False


def test_tamper_evident_hash_chain():
    h1 = compute_audit_hash(
        previous_hash=GENESIS_HASH,
        event_type="SUBMISSION_CREATED",
        entity_type="PARCEL",
        entity_id="12345678901234",
        actor_id="builder.demo",
        timestamp_iso="2026-09-24T10:00:00Z",
        payload={"action": "test"},
    )
    assert len(h1) == 64

    h2 = compute_audit_hash(
        previous_hash=h1,
        event_type="VERIFICATION_APPROVED",
        entity_type="PARCEL",
        entity_id="12345678901234",
        actor_id="district.admin",
        timestamp_iso="2026-09-24T10:30:00Z",
        payload={"decision": "APPROVED"},
    )
    assert len(h2) == 64
    assert h1 != h2
