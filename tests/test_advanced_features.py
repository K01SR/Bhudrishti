import json
import pytest
from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_precinct_recovery_never_prices_an_invented_fsi_ceiling():
    """
    B-03 and B-09 used to carry a priced "excess" FSI computed against a 2.0
    ceiling that the scenario itself invented -- no DCR was ever read for those
    plots. That shortfall was then levied as evaded tax, doubled as a Sec 267A
    penalty and compounded, so an invented limit became a rupee figure. Without
    a sanctioned ceiling there is no excess area to assess, so those buildings
    are not in the breakdown at all.
    """
    res = client.get("/api/v1/precinct/revenue-recovery")
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "breakdown" in data
    assert data["ready_reckoner_rate_is_illustrative"] is True
    assert data["provenance"]["is_synthetic"] is True

    codes = {b["building_code"] for b in data["breakdown"]}
    assert "B-03" not in codes
    assert "B-09" not in codes
    # The two scenario buildings whose area comes from their own footprint and
    # built-up area rather than from a fabricated FSI limit are still reported.
    assert {"B-17", "B-12"} <= codes
    assert data["summary"]["total_flagged_properties"] == len(data["breakdown"])

    b17 = next(b for b in data["breakdown"] if b["building_code"] == "B-17")
    assert b17["action"] == "DEMOLITION_ORDER_MANDATORY"
    assert b17["unassessed_built_up_m2"] == 510.0


def test_statutory_demand_notice_generation(authed_verify):
    # Test demolition notice for B-17
    client = authed_verify
    res = client.post(
        "/api/v1/precinct/generate-demand-notice",
        json={"building_code": "B-17", "notice_type": "SEC_260_DEMOLITION"}
    )
    assert res.status_code == 200
    notice = res.json()
    # The notice number must not impersonate a municipal register: it previously
    # read "NMMC/TPO/2026/B-17/...".
    assert notice["notice_number"].startswith("SIMULATED/")
    assert "NMMC" not in notice["notice_number"]
    assert "DEMOLITION" in notice["legal_notice_title"]
    assert notice["financial_demand"]["total_payable_inr"] > 0
    # The fake "SHA256-ED25519-NMMC-SEAL" block is gone; a bare sha256 of a string
    # is not a signature and must not be presented as a seal.
    # Genuinely signed now, not fabricated. Previously this asserted the field
    # was None, which was the correct state when the alternative was a bare
    # sha256() under a fake "SHA256-ED25519-NMMC-SEAL" label. The claim has to
    # be real, so the check is that it is a real Ed25519 signature over a real
    # SHA-256 fingerprint, and that it names no authority.
    crypto = notice["cryptographic_verification"]
    assert crypto is not None
    assert crypto["algorithm"] == "Ed25519"
    assert crypto["status"] == "SELF_SIGNED_BY_THIS_SERVICE"
    assert len(crypto["sha256_fingerprint"]) == 64
    assert len(crypto["ed25519_signature"]) == 128
    assert "NMMC" not in json.dumps(crypto)
    assert notice["issuing_authority"] is None


def test_buyer_shield_verification_illegal_floor():
    # 6th floor unit on B-17 (unauthorized floor)
    res = client.get("/api/v1/precinct/buyer-shield/verify/12345678901234/UB17-L06-601-A")
    assert res.status_code == 200
    audit = res.json()
    assert audit["overall_grade"] == "F"
    assert audit["verdict"]["safe_for_purchase"] is False
    assert audit["verdict"]["bank_loan_eligible"] is False
    # Check that the as-built concordance scenario failed
    lidar_check = next((c for c in audit["checks"] if "As-Built" in c["pillar"]), None)
    assert lidar_check is not None
    assert lidar_check["passed"] is False
    # ...and that it is labelled a scenario rather than a survey finding.
    assert "SIMULATED" in lidar_check["pillar"]


def test_buyer_shield_verification_compliant_unit():
    # Approved 5th floor unit on B-17
    res = client.get("/api/v1/precinct/buyer-shield/verify/12345678901234/UB17-L05-501-A")
    assert res.status_code == 200
    audit = res.json()
    assert audit["overall_grade"] == "A+"
    assert audit["verdict"]["safe_for_purchase"] is True
    assert audit["verdict"]["bank_loan_eligible"] is True


def test_subsurface_network_and_clash_detection(authed_verify):
    # Get subsurface network
    client = authed_verify
    net_res = client.get("/api/v1/precinct/subsurface/network")
    assert net_res.status_code == 200
    net = net_res.json()
    assert net["total_utilities"] >= 4

    # Test direct collision with PNG gas pipeline at [170, 100]
    clash_res = client.post(
        "/api/v1/precinct/subsurface/clash-test",
        json={"x": 170.0, "y": 100.0, "depth_m": 3.0, "radius_m": 1.0, "work_type": "Borewell Piling"}
    )
    assert clash_res.status_code == 200
    clash_data = clash_res.json()
    assert clash_data["status"] == "CRITICAL_COLLISION"
    assert clash_data["clearance_granted"] is False
    assert clash_data["clashes_count"] >= 1

    # Test clear excavation point far away from utilities
    safe_res = client.post(
        "/api/v1/precinct/subsurface/clash-test",
        json={"x": 80.0, "y": 80.0, "depth_m": 2.0, "radius_m": 0.8, "work_type": "Drain Trench"}
    )
    assert safe_res.status_code == 200
    safe_data = safe_res.json()
    assert safe_data["status"] == "SAFE"
    assert safe_data["clearance_granted"] is True
    # No permit reference may be issued: the old value was a CBYD-NMMC-2026-*
    # string derived from the clock, which reads as municipal authorisation.
    assert safe_data["cbyd_permit_number"] is None
    assert "not a dig-safety clearance" in safe_data["clearance_note"]
