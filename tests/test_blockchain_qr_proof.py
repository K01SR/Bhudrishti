"""
Tests for the signed blockchain QR proof.

The point of these tests is not that the code returns True. It is that a proof
that has been altered in any way is caught, and that a proof carrying no
signature is reported as unsigned rather than quietly counted as valid.
"""
import copy
import json
import urllib.parse

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.blockchain import (
    get_cadastral_blockchain,
    verify_qr_proof,
    signed_body_from_payload,
    TransactionNotFound,
    PROOF_SIGNED_FIELDS,
)

client = TestClient(app)


@pytest.fixture
def proof():
    return get_cadastral_blockchain().generate_qr_proof("20260925000003")


def test_proof_is_signed_not_just_hashed(proof):
    """A proof with only hashes proves nothing, so it must carry a signature."""
    assert proof["sha256_fingerprint"]
    assert proof["ed25519_signature"]
    assert proof["public_key_hex"]
    # The signature must actually be a signature length, not a truncated hash.
    assert len(proof["ed25519_signature"]) == 128


def test_untouched_proof_verifies_on_both_axes(proof):
    result = verify_qr_proof(proof)
    assert result["signature_valid"] is True
    assert result["merkle_path_valid"] is True
    assert result["fingerprint_matches"] is True


def test_merkle_path_is_independent_of_the_signature(proof):
    """
    Rewriting a signed field must break the signature, but the underlying
    transaction is still in the block, so the Merkle path still holds.

    This is the distinction the UI reports. Collapsing it into one boolean
    would hide a tampered payload that still looks structurally sound.
    """
    tampered = copy.deepcopy(proof)
    tampered["ulpin"] = "X-SRC-99999999"
    result = verify_qr_proof(tampered)
    assert result["signature_valid"] is False
    assert result["fingerprint_matches"] is False
    assert result["merkle_path_valid"] is True


def test_forged_merkle_root_is_caught(proof):
    tampered = copy.deepcopy(proof)
    tampered["merkle_root"] = "f" * 64
    result = verify_qr_proof(tampered)
    assert result["merkle_path_valid"] is False
    assert result["signature_valid"] is False


def test_forged_merkle_proof_is_caught(proof):
    tampered = copy.deepcopy(proof)
    tampered["merkle_proof"] = [{"position": "left", "sibling_hash": "a" * 64}]
    result = verify_qr_proof(tampered)
    assert result["merkle_path_valid"] is False
    assert result["signature_valid"] is False


def test_signature_swapped_from_another_proof_is_caught(proof):
    """
    A valid signature lifted off a different proof must not verify against this
    one, or the signature would be a decorative field anyone could copy.
    """
    other = get_cadastral_blockchain().generate_qr_proof("20260925000012")
    forged = copy.deepcopy(proof)
    forged["ed25519_signature"] = other["ed25519_signature"]
    result = verify_qr_proof(forged)
    assert result["signature_valid"] is False


def test_unsigned_proof_is_reported_unsigned_not_valid(proof):
    """
    Removing the signature must yield an explanation, not a silent pass. The
    Merkle path can still be checked without a key, and that has to stay true.
    """
    unsigned = copy.deepcopy(proof)
    unsigned.pop("ed25519_signature")
    result = verify_qr_proof(unsigned)
    assert result["signature_valid"] is False
    assert result["signature_error"]
    assert result["merkle_path_valid"] is True


def test_missing_signed_fields_are_rejected(proof):
    incomplete = copy.deepcopy(proof)
    del incomplete["validator"]
    result = verify_qr_proof(incomplete)
    assert result["signature_valid"] is False
    assert result["merkle_path_valid"] is False
    assert "validator" in result["error"]


def test_signed_body_selection_is_an_explicit_allow_list(proof):
    """
    The signature must cover only the intended fields, and rebuilding the body
    from a received payload must ignore anything extra a scanner might carry.
    """
    body = signed_body_from_payload(proof)
    assert set(body) == set(PROOF_SIGNED_FIELDS)
    # These are outside the signature by necessity, so they must not sneak in.
    assert "ed25519_signature" not in body
    assert "sha256_fingerprint" not in body

    polluted = copy.deepcopy(proof)
    polluted["injected"] = "attacker"
    assert "injected" not in signed_body_from_payload(polluted)


def test_verify_url_is_self_contained(proof):
    """
    A proof a third party can only check by asking this server proves nothing
    once the server is unreachable, so the link must carry the whole payload.
    """
    url = proof["verify_url"]
    assert "/verify/blockchain?p=" in url

    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    carried = json.loads(query["p"][0])

    # Verifiable straight from the link, with no other input.
    result = verify_qr_proof(carried)
    assert result["signature_valid"] is True
    assert result["merkle_path_valid"] is True


def test_verify_url_excludes_itself_to_avoid_recursion(proof):
    query = urllib.parse.parse_qs(urllib.parse.urlparse(proof["verify_url"]).query)
    carried = json.loads(query["p"][0])
    assert "verify_url" not in carried


def test_unknown_identifier_issues_no_proof():
    """
    Regression guard for the bug that made this feature unsafe.

    An unknown ULPIN used to fall back to the Unit 501 / B-17 hero record, so
    requesting a parcel that does not exist returned a genuine, correctly signed
    proof for a different property, and two different unknown identifiers
    produced byte-identical proofs. A signed QR could therefore be obtained for
    a parcel that was never in the ledger.
    """
    bc = get_cadastral_blockchain()
    for unknown in ("X-SRC-FFD75F51", "X-SRC-08DA5F9C", "not-a-real-parcel"):
        with pytest.raises(TransactionNotFound):
            bc.generate_qr_proof(unknown)


def test_unknown_identifier_returns_404_not_a_substitute_proof():
    response = client.get("/api/v1/blockchain/qr-proof/X-SRC-FFD75F51")
    assert response.status_code == 404
    # A 404 must not carry a proof body a client could mistake for success.
    assert "ed25519_signature" not in response.json()


def test_merkle_path_is_vacuous_while_blocks_hold_one_transaction():
    """
    Every block in this prototype ledger holds a single transaction, so its
    Merkle proof is empty and the path check reduces to leaf == root.

    The check is still worth running, because it catches an edited root, but it
    is not yet evidence of much. Asserted here so that the day a block does gain
    several transactions, this test fails and the real coverage gets written
    instead of the suite quietly implying the path is exercised.
    """
    bc = get_cadastral_blockchain()
    assert all(len(block.transactions) == 1 for block in bc.chain)
    assert bc.generate_qr_proof("20260925000003")["merkle_proof"] == []


def test_published_demo_key_is_disclosed(proof):
    """
    The demo keypair is published in this repository, so a proof signed with it
    identifies the software and not a person. That must be surfaced, because a
    valid signature otherwise reads as an official endorsement.
    """
    result = verify_qr_proof(proof)
    assert result["signature_uses_published_demo_key"] is True


def test_endpoint_is_reachable_without_authentication(proof):
    """A verifier that needs a login is not a verifier."""
    response = client.post("/api/v1/blockchain/qr-proof/verify", json=proof)
    assert response.status_code == 200
    body = response.json()
    assert body["signature_valid"] is True
    assert body["merkle_path_valid"] is True


def test_endpoint_does_not_swallow_verify_as_an_identifier(proof):
    """
    "/qr-proof/{identifier}" is declared after this route, but that ordering is
    load-bearing: if it ever moves, the literal segment "verify" gets read as a
    parcel name and the check silently returns a proof for a non-existent
    property instead of running.
    """
    lookup = client.get("/api/v1/blockchain/qr-proof/20260925000003")
    assert lookup.status_code == 200
    assert "ed25519_signature" in lookup.json()

    response = client.post("/api/v1/blockchain/qr-proof/verify", json=proof)
    assert response.status_code == 200
    assert "signature_valid" in response.json()


def test_endpoint_states_what_a_pass_does_not_mean(proof):
    """A bare "verified" is read as "the government confirmed this property"."""
    body = client.post("/api/v1/blockchain/qr-proof/verify", json=proof).json()
    disclosure = body["disclosure"]
    assert disclosure["does_not_prove"]
    assert any("government" in line.lower() for line in disclosure["does_not_prove"])
