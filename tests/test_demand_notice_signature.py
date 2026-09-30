"""The demand notice's Ed25519 signature must be real and must round-trip.

This endpoint has a history worth recording, because each version of it was
wrong in a different direction:

1. It reported ``"algorithm": "SHA256-ED25519-NMMC-SEAL"`` over a bare
   ``sha256()`` of a string. There was no key and no signature. It named the
   Municipal Commissioner as signatory and published a verification URL on
   ``bhudrishti.maharashtra.gov.in``, which resolves to nothing.
2. That was corrected to ``"cryptographic_verification": None`` -- honest, but
   it also threw away the one thing that could have been genuinely true.
3. Now it signs. The claim is narrow and the tests below hold it to that narrow
   claim: a real Ed25519 signature over the real SHA-256 fingerprint of the
   real document, verifiable, failing on any tamper.

The failure mode these tests exist to catch is a signature that is *present but
unverifiable*, which looks identical to a working one in a UI screenshot. Hence
the round-trip assertion rather than a "field is not null" check.
"""
from __future__ import annotations


import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    from app.main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def notice(client: TestClient) -> dict:
    token = client.post(
        "/api/v1/auth/login",
        data={"username": "state.admin", "password": "demo@2026"},
    ).json()["access_token"]
    res = client.post(
        "/api/v1/precinct/generate-demand-notice",
        json={"building_code": "B-17", "notice_type": "SEC_260_DEMOLITION"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_notice_carries_a_real_signature(notice: dict) -> None:
    block = notice["cryptographic_verification"]
    assert block is not None, "the notice is unsigned; the endpoint should sign"
    assert block["algorithm"] == "Ed25519"
    # A real SHA-256 is 32 bytes of hex, a real Ed25519 signature 64 bytes of
    # hex. Asserted by length so a truncated or doubled digest cannot pass.
    assert len(block["sha256_fingerprint"]) == 64
    assert len(block["ed25519_signature"]) == 128
    assert block["status"] == "SELF_SIGNED_BY_THIS_SERVICE"


def test_signature_verifies_against_the_returned_document(client: TestClient, notice: dict) -> None:
    """The whole point: an untampered document must verify.

    This is the assertion that catches the bug it is written for. An earlier
    implementation signed the document and then appended two explanatory fields
    to the response, so the bytes a verifier could reconstruct never matched the
    bytes that were signed, and every verification of a genuine document
    returned False. Nothing in a screenshot or a "field is not null" check would
    have shown that.
    """
    sig = notice["cryptographic_verification"]["ed25519_signature"]
    res = client.post(
        "/api/v1/precinct/verify-signature",
        json={"document": notice, "ed25519_signature": sig},
    )
    assert res.status_code == 200, res.text
    assert res.json()["valid"] is True


def test_tampered_document_fails_verification(client: TestClient, notice: dict) -> None:
    """Changing the rupee figure must invalidate the signature.

    A signature that survives a changed amount is not a signature; it is
    decoration. The amount is the field a reader would most want protected.
    """
    sig = notice["cryptographic_verification"]["ed25519_signature"]
    tampered = dict(notice)
    tampered["financial_demand"] = dict(notice["financial_demand"])
    tampered["financial_demand"]["total_payable_inr"] = 1
    res = client.post(
        "/api/v1/precinct/verify-signature",
        json={"document": tampered, "ed25519_signature": sig},
    )
    assert res.json()["valid"] is False


def test_verification_never_claims_official_status(client: TestClient, notice: dict) -> None:
    """
    A valid signature is still not an official record.

    The failure this prevents is the one the original fake seal made: a
    verification endpoint that returns `valid: true` and lets a reader infer a
    government guarantee. `valid` means the bytes are unaltered. Nothing more,
    and the response has to say so in words as well as in a boolean.
    """
    sig = notice["cryptographic_verification"]["ed25519_signature"]
    body = client.post(
        "/api/v1/precinct/verify-signature",
        json={"document": notice, "ed25519_signature": sig},
    ).json()
    assert body["is_official_record"] is False
    assert body["disclosure"]["signature_algorithm"] == "Ed25519"
    assert "does not establish who created the record" in body["does_not_verify"]


def test_no_government_seal_or_authority_is_claimed(client: TestClient, notice: dict) -> None:
    """
    No response field may name a government seal, office or verification host.

    Checked against the rendered payload rather than the source text, because
    the module's docstrings deliberately quote the removed claims in order to
    document them -- "SHA256-ED25519-NMMC-SEAL" and the government verification
    URL are both still present in prose, explaining why they are gone. A
    source-text ban would forbid the changelog.

    So this asserts on what a caller actually receives: no municipal seal label,
    no signatory, no government domain, and a null issuing authority.
    """
    import json

    blob = json.dumps(notice)
    for banned in ("NMMC-SEAL", "Municipal Commissioner", "bhudrishti.maharashtra.gov.in"):
        assert banned not in blob, f"the response still claims {banned!r}"
    assert notice["issuing_authority"] is None
    assert "NOT A LEGAL INSTRUMENT" in notice["document_type"]
