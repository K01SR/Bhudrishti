import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.blockchain import get_cadastral_blockchain, MerkleTree, Transaction, SmartContractEngine

client = TestClient(app)

def test_merkle_tree_construction_and_verification():
    tx_hashes = [
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "d" * 64
    ]
    tree = MerkleTree(tx_hashes)
    assert len(tree.root) == 64
    proof = tree.get_proof(tx_hashes[0])
    assert len(proof) > 0
    is_valid = MerkleTree.verify_proof(tx_hashes[0], proof, tree.root)
    assert is_valid is True

def test_smart_contracts():
    # FSI comparison. This used to assert passed/status == "APPROVED" and
    # "REJECTED_BREACH_DETECTED", and it cited "UDCPR 2020 Sec 3.4.1" as the
    # basis while raising the possibility of a TRIGGER_PENALTY_NOTICE. No
    # sanctioned plan is loaded and no regulation is read, so it can only report
    # a ratio against the limit the caller supplied.
    fsi_ok = SmartContractEngine.evaluate_fsi_contract(built_up_m2=2000.0, plot_area_m2=1000.0, max_allowed_fsi=2.0)
    assert fsi_ok["within_caller_supplied_limit"] is True
    assert fsi_ok["status"] == "COMPARED"
    assert fsi_ok["statutory_ref"] is None
    assert fsi_ok["enforcement"] is None

    fsi_bad = SmartContractEngine.evaluate_fsi_contract(built_up_m2=2500.0, plot_area_m2=1000.0, max_allowed_fsi=2.0)
    assert fsi_bad["within_caller_supplied_limit"] is False
    assert fsi_bad["status"] == "COMPARED"
    assert fsi_bad["statutory_ref"] is None

    # Multi-Sig
    sig_ok = SmartContractEngine.evaluate_multi_sig_gate({"BUILDER": "s1", "DISTRICT_VERIFIER": "s2"})
    assert sig_ok["passed"] is True

    sig_bad = SmartContractEngine.evaluate_multi_sig_gate({"BUILDER": "s1"})
    assert sig_bad["passed"] is False

def test_blockchain_api_blocks_and_integrity():
    # Blocks list
    res = client.get("/api/v1/blockchain/blocks")
    assert res.status_code == 200
    data = res.json()
    assert data["total_blocks"] >= 10
    assert len(data["blocks"]) >= 10

    # Block detail
    res_b = client.get("/api/v1/blockchain/blocks/5")
    assert res_b.status_code == 200
    assert res_b.json()["index"] == 5
    assert "merkle_root" in res_b.json()

    # Blockchain stats
    res_s = client.get("/api/v1/blockchain/stats")
    assert res_s.status_code == 200
    assert res_s.json()["chain_health"] == "VALID"

    # Verify chain
    res_v = client.get("/api/v1/blockchain/verify")
    assert res_v.status_code == 200
    assert res_v.json()["integrity"] == "VALID"

def test_blockchain_tamper_and_self_healing(authed_state):
    client = authed_state
    # Tamper with block 5
    res_t = client.post("/api/v1/blockchain/tamper-simulate", json={
        "block_index": 5,
        "field": "consideration_inr",
        "malicious_value": 999
    })
    assert res_t.status_code == 200
    assert res_t.json()["action"] == "TAMPER_INJECTED"

    # Check verify endpoint detects corruption
    res_v = client.get("/api/v1/blockchain/verify")
    assert res_v.status_code == 200
    assert res_v.json()["integrity"] == "CORRUPTED"
    assert res_v.json()["broken_block_index"] == 5

    # Self-heal from consensus
    res_h = client.post("/api/v1/blockchain/self-heal")
    assert res_h.status_code == 200
    assert res_h.json()["status"] == "CHAIN_RESTORED"

    # Check verify is VALID again
    res_v2 = client.get("/api/v1/blockchain/verify")
    assert res_v2.status_code == 200
    assert res_v2.json()["integrity"] == "VALID"

def test_excel_templates_and_3d_extrusion(authed_verify):
    client = authed_verify
    # Download Excel template
    res_tpl_xlsx = client.get("/api/v1/ids/template/excel")
    assert res_tpl_xlsx.status_code == 200
    assert len(res_tpl_xlsx.content) > 1000

    # Download CSV template
    res_tpl_csv = client.get("/api/v1/ids/template/csv")
    assert res_tpl_csv.status_code == 200
    assert "Building_Code" in res_tpl_csv.text

    # Upload Excel file for 3D extrusion
    res_extrude = client.post(
        "/api/v1/ids/generate-from-spreadsheet",
        files={"file": ("sample.xlsx", res_tpl_xlsx.content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert res_extrude.status_code == 200
    ext_data = res_extrude.json()
    assert ext_data["status"] == "SUCCESS_EXTRUDED_FROM_SPREADSHEET"
    assert ext_data["total_buildings_generated"] >= 1
    assert ext_data["total_3d_ulpins_minted"] >= 5
    assert "threejs_geometry" in ext_data["buildings"][0]

def test_latex_and_pdf_exports():
    # PDF Property Card
    res_pdf = client.get("/api/v1/exports/pdf/property-card/12345678901234")
    assert res_pdf.status_code == 200
    assert res_pdf.content.startswith(b"%PDF")

    # LaTeX Source
    res_tex = client.get("/api/v1/exports/latex/property-card/12345678901234")
    assert res_tex.status_code == 200
    assert "\\documentclass" in res_tex.text
    assert "12345678901234" in res_tex.text

    # Excel Cadastral Register
    res_xl = client.get("/api/v1/exports/excel/cadastre")
    assert res_xl.status_code == 200
    assert len(res_xl.content) > 2000


def test_chain_asserts_no_third_party_attestation():
    """
    The chain advertised authority it never had. Block headers carried three
    "multi-signatures" that were SHA-256 digests of a constant string keyed by
    block index, labelled NMMC_REVENUE_AUTHORITY, MAHARERA_GATEWAY and
    SURVEY_OF_INDIA. Seed transactions carried ten fake `ed25519:` values
    attributed to an OFFICER, BUILDER, TOWN_PLANNER, SELLER, BUYER, REGISTRAR
    and CITIZEN_REP. None of them is a signature over anything, so every one
    asserted a government or party endorsement that did not exist.
    """
    bc = get_cadastral_blockchain()

    for block in bc.chain:
        assert not block.multi_signatures, (
            f"block {block.index} claims signers: {sorted(block.multi_signatures)}"
        )
        for tx in block.transactions:
            assert not tx.signatures, (
                f"tx {tx.tx_id[:12]} claims signers: {sorted(tx.signatures)}"
            )
            for value in tx.signatures.values():
                assert not value.startswith("ed25519:"), "fabricated signature literal"

    # An empty mapping is the honest state; the renderer in AuditPage falls back
    # to an explicit "no third party has signed this block" label.
    payload = client.get("/api/v1/blockchain/blocks").json()
    for block in payload["blocks"]:
        assert block.get("multi_signatures") == {}


def test_chain_advertises_no_unconfigured_peers_or_contract_addresses():
    """
    Five peer nodes were listed on .gov.in hostnames that were never resolved
    or contacted, and four "smart contracts" carried invented hex addresses
    implying a published deployment that does not exist. Both are now empty or
    local references.
    """
    bc = get_cadastral_blockchain()

    assert bc.peer_nodes == [], f"unconfigured peers advertised: {bc.peer_nodes}"

    for name, ref in bc.smart_contracts.items():
        assert not ref.startswith("0x"), f"{name} still claims a deployed address: {ref}"
        assert "http" not in ref, f"{name} still claims a network endpoint: {ref}"


def test_stats_state_root_is_the_genesis_hash():
    """
    `/stats` returned a hardcoded state root that matched no block in the
    chain, so it read as a verified commitment while agreeing with nothing
    recomputable. It must now be the genesis block hash itself.
    """
    stats = client.get("/api/v1/blockchain/stats").json()
    blocks = client.get("/api/v1/blockchain/blocks").json()["blocks"]

    genesis_hash = next(b["block_hash"] for b in blocks if b["index"] == 0)
    assert stats["state_root"] == genesis_hash
    assert stats["state_root"] in {b["block_hash"] for b in blocks}


def test_chain_restore_reports_no_peer_consensus():
    """
    `self_heal_from_consensus` restores from a local in-memory snapshot, but
    returned "5_OF_5_PEERS_AGREED" and was documented as querying peer nodes.
    No peer is ever contacted, so the count described agreement between no one.
    """
    bc = get_cadastral_blockchain()
    snapshot = bc._backup_consensus_state
    assert snapshot, "the seed chain is expected to record a self-heal snapshot"

    result = bc.self_heal_from_consensus()

    assert result["peer_consensus"] == "NO_PEERS_CONFIGURED"
    assert result["verification"]["integrity"] == "VALID"
    assert result["restored_blocks_count"] == len(snapshot)
