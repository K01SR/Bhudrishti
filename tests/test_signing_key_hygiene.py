"""The Ed25519 keypair must never be a committed default again.

A private key in a tracked file is published to everyone who clones the
repository. The pair that lived in ``config.py`` and ``.env.example`` since
the first commit meant that anyone could produce a signature this deployment
would accept as valid, which is the opposite of what a signature is for.

The published pair still exists, but only as a demonstration fixture in
``app.core.crypto``, reachable while ``ENABLE_DEMO_MODE`` is on and refused
when ``ENVIRONMENT`` is production.
"""
import pytest

from app.core import crypto
from app.core.config import Settings
from app.core.crypto import SigningKeyNotConfigured, sign_canonical_record


RECORD = {"ulpin": "12345678901234", "kind": "demo"}


def test_no_keypair_is_configured_by_default():
    settings = Settings(_env_file=None)
    assert settings.ED25519_PRIVATE_KEY_HEX is None
    assert settings.ED25519_PUBLIC_KEY_HEX is None


def test_demo_keypair_is_not_a_config_default():
    """The published pair must not be reachable as a fallback for real data."""
    from app.core.config import settings as live

    assert live.ED25519_PRIVATE_KEY_HEX is None
    assert live.ED25519_PUBLIC_KEY_HEX is None
    assert crypto.DEMO_ED25519_PRIVATE_KEY_HEX != crypto.DEMO_ED25519_PUBLIC_KEY_HEX


def test_signing_uses_the_demo_key_only_while_the_demo_gate_is_open(monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    fingerprint, signature = sign_canonical_record(RECORD)
    assert crypto.verify_record_signature(RECORD, signature) is True
    assert len(fingerprint) == 64 and len(signature) == 128


def test_signing_refuses_without_a_key_or_the_demo_gate(monkeypatch):
    """
    With the gate shut and no key configured, signing must fail loudly rather
    than quietly falling back to the published key. Falling back would let a
    real deployment issue records signed by a key the world already has.
    """
    monkeypatch.setenv("ENABLE_DEMO_MODE", "0")
    settings = Settings(_env_file=None)
    monkeypatch.setattr(crypto.settings, "ED25519_PRIVATE_KEY_HEX", None, raising=False)

    with pytest.raises(SigningKeyNotConfigured):
        crypto._resolve_private_key_hex()


def test_demo_keypair_is_refused_in_production(monkeypatch):
    """
    Even an operator who configures the published key explicitly must not be
    able to boot a production deployment that signs with it.
    """
    monkeypatch.setattr(crypto.settings, "ENVIRONMENT", "production", raising=False)
    monkeypatch.setattr(
        crypto.settings, "ED25519_PRIVATE_KEY_HEX",
        crypto.DEMO_ED25519_PRIVATE_KEY_HEX, raising=False,
    )
    with pytest.raises(SigningKeyNotConfigured):
        crypto._resolve_private_key_hex()

    monkeypatch.setattr(
        crypto.settings, "ED25519_PUBLIC_KEY_HEX",
        crypto.DEMO_ED25519_PUBLIC_KEY_HEX, raising=False,
    )
    with pytest.raises(SigningKeyNotConfigured):
        crypto._resolve_public_key_hex()


def test_configured_production_keypair_is_accepted(monkeypatch):
    """A distinct keypair in production is the supported path and must work."""
    from cryptography.hazmat.primitives.asymmetric import ed25519 as _ed

    key = _ed.Ed25519PrivateKey.generate()
    monkeypatch.setattr(crypto.settings, "ENVIRONMENT", "production", raising=False)
    monkeypatch.setattr(
        crypto.settings, "ED25519_PRIVATE_KEY_HEX",
        key.private_bytes_raw().hex(), raising=False,
    )
    monkeypatch.setattr(
        crypto.settings, "ED25519_PUBLIC_KEY_HEX",
        key.public_key().public_bytes_raw().hex(), raising=False,
    )

    assert crypto._resolve_private_key_hex() == key.private_bytes_raw().hex()
    _, signature = sign_canonical_record(RECORD)
    assert crypto.verify_record_signature(RECORD, signature) is True
    # A record that was not signed is still rejected.
    assert crypto.verify_record_signature({**RECORD, "kind": "other"}, signature) is False


def test_missing_key_is_not_reported_as_an_invalid_signature(monkeypatch):
    """
    `verify_record_signature` catches broadly and returns False. Key resolution
    must sit outside that block, or a deployment with no key would report every
    record as unverified and give no indication why.
    """
    monkeypatch.setenv("ENABLE_DEMO_MODE", "0")
    monkeypatch.setattr(crypto.settings, "ED25519_PUBLIC_KEY_HEX", None, raising=False)

    with pytest.raises(SigningKeyNotConfigured):
        crypto.verify_record_signature(RECORD, "00" * 64)


def test_committed_key_is_never_bound_to_a_config_field():
    """
    Guards the two files a key was previously committed to, so a future
    convenience edit cannot quietly reintroduce a usable default.

    config.py is allowed to name the published pair inside the production
    denylist, because the guard has to recognise it in order to reject it. What
    must never happen is the key being bound to a settings field, which is what
    made it a default.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    key = crypto.DEMO_ED25519_PRIVATE_KEY_HEX
    pub = crypto.DEMO_ED25519_PUBLIC_KEY_HEX

    for rel in ("backend/app/core/config.py", ".env.example"):
        text = (root / rel).read_text()
        for field, value in (
            ("ED25519_PRIVATE_KEY_HEX", key),
            ("ED25519_PUBLIC_KEY_HEX", pub),
        ):
            bound = re.search(rf"{field}\s*[:=]\s*[\"']?{re.escape(value)}", text)
            assert bound is None, f"{rel} binds {field} to the published demo key"

    # The example env must not carry the key at all, not even commented out.
    assert key not in (root / ".env.example").read_text()


def test_integrity_score_claims_no_official_verification():
    """
    The integrity scorecard counted a factor labelled "Official verification
    stamp" as PASS with zero weight, on the detail "Record V1.0 APPROVED and
    Ed25519-signed by Thane District Land Records Verifier". No such stamp or
    signature exists, and a zero-weight PASS is the strongest possible claim in
    a score.
    """
    import json as _json

    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    res = client.get("/api/v1/integrity/properties/12345678901234")
    assert res.status_code == 200, res.text
    body = _json.dumps(res.json())

    for forged in (
        "Official verification stamp",
        "Thane District Land Records Verifier",
        "Ed25519-signed by",
        "verified at municipality level",
    ):
        assert forged not in body, f"integrity scorecard still claims {forged!r}"

    factors = res.json().get("factors") or res.json().get("checks") or []
    for factor in factors:
        if factor.get("key") == "verification":
            assert factor["status"] != "PASS"
            assert factor["weight"] != 0


def test_no_endpoint_attributes_a_signature_to_an_authority():
    """
    Sweeps the public responses for a signature attributed to a named office.
    properties.py and verification.py both returned signer_authority naming the
    Thane District Land Records Verifier with no signature behind it.
    """
    import json as _json

    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    res = client.get("/api/v1/properties/hero")
    assert res.status_code == 200, res.text

    proof = res.json()["cryptographic_proof"]
    assert proof["signer_authority"] is None
    assert proof["verification_status"] == "SELF_SIGNED_BY_THIS_SERVICE"

    body = _json.dumps(res.json())
    for forged in (
        "Thane District Land Records Verifier",
        "CRYPTOGRAPHICALLY_VERIFIED",
        "APPROVED_AND_CRYPTOGRAPHICALLY_SIGNED",
    ):
        assert forged not in body, f"response still claims {forged!r}"
