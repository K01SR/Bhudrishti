import pytest
from app.id_engine.generator import (
    generate_proposed_3d_id,
    parse_and_validate_3d_id,
    calculate_luhn_mod36_checksum,
    verify_luhn_mod36_checksum,
)
from app.id_engine.types import SpatialTypeCode


def test_generate_3d_id():
    parent_ulpin = "12345678901234"
    generated = generate_proposed_3d_id(
        parent_ulpin=parent_ulpin,
        type_code="U",
        building_code="B17",
        level_code="L05",
        unit_code="501",
    )
    assert generated.startswith("12345678901234/UB17-L05-501-")
    assert len(generated.split("-")) == 4


def test_luhn_mod36_checksum_deterministic():
    payload = "12345678901234/UB17-L05-501"
    check1 = calculate_luhn_mod36_checksum(payload)
    check2 = calculate_luhn_mod36_checksum(payload)
    assert check1 == check2
    assert check1 in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def test_parse_and_validate_valid_id():
    parent_ulpin = "12345678901234"
    valid_id = generate_proposed_3d_id(parent_ulpin, "U", "B17", "L02", "201")
    parsed = parse_and_validate_3d_id(valid_id)

    assert parsed.is_valid is True
    assert parsed.parent_ulpin == "12345678901234"
    assert parsed.type_code == SpatialTypeCode.UNIT
    assert parsed.level_code == "L02"
    assert parsed.unit_code == "201"


def test_parse_corrupted_id():
    parent_ulpin = "12345678901234"
    valid_id = generate_proposed_3d_id(parent_ulpin, "U", "B17", "L02", "201")
    # Mutate checksum
    corrupted_id = valid_id[:-1] + ("0" if valid_id[-1] != "0" else "1")
    parsed = parse_and_validate_3d_id(corrupted_id)
    assert parsed.is_valid is False
    assert "Checksum mismatch" in parsed.validation_message


def test_all_spatial_types():
    parent = "12345678901234"
    for type_code in [
        SpatialTypeCode.SURFACE,
        SpatialTypeCode.BUILDING,
        SpatialTypeCode.LEVEL,
        SpatialTypeCode.UNIT,
        SpatialTypeCode.UNDERGROUND,
        SpatialTypeCode.ELEVATED,
        SpatialTypeCode.AIR_RIGHT,
        SpatialTypeCode.PARKING,
    ]:
        gen = generate_proposed_3d_id(parent, type_code.value, "B17", "G", "01")
        parsed = parse_and_validate_3d_id(gen)
        assert parsed.is_valid is True


def test_precinct_all_buildings_have_valid_3d_ulpins():
    """Verify that all 13 buildings and all 460+ vertical units have valid 3D ULPINs."""
    from app.pipelines.synthetic_generator import generate_synthetic_airoli_dataset
    dataset = generate_synthetic_airoli_dataset()
    precinct_buildings = dataset.get("precinct_buildings", [])
    assert len(precinct_buildings) == 12

    total_units_checked = 0
    for b in precinct_buildings:
        # Building master 3D ULPIN
        b_3d_id = b.get("proposed_3d_id")
        assert b_3d_id is not None
        p_bldg = parse_and_validate_3d_id(b_3d_id)
        assert p_bldg.is_valid is True, f"Invalid building 3D-ID: {b_3d_id} ({p_bldg.validation_message})"

        # Constituent vertical units
        units = b.get("units", [])
        assert len(units) > 0
        for u in units:
            u_id = u.get("proposed_3d_id")
            assert u_id is not None
            p_unit = parse_and_validate_3d_id(u_id)
            assert p_unit.is_valid is True, f"Invalid unit 3D-ID: {u_id} ({p_unit.validation_message})"
            total_units_checked += 1

    assert total_units_checked >= 440


def test_precinct_3d_id_catalogue_api():
    """Verify the /ids/precinct and /ids/building/{code} API endpoints."""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)

    res = client.get("/api/v1/ids/precinct")
    assert res.status_code == 200
    data = res.json()
    assert data["total_buildings"] >= 13
    assert data["total_3d_ids"] >= 460
    assert len(data["buildings"]) >= 13

    # Check building B-01 endpoint
    res_b01 = client.get("/api/v1/ids/building/B-01")
    assert res_b01.status_code == 200
    b01_data = res_b01.json()
    assert b01_data["code"] == "B-01"
    assert b01_data["units_count"] == 50
    assert all(u["is_valid"] is True for u in b01_data["units"])


def test_unextruded_parcels_and_extrusion_pipeline(authed_state):
    """Verify scanning of unextruded 2D parcels and on-demand 3D-ULPIN minting."""
    from fastapi.testclient import TestClient
    client = authed_state

    # 1. Check unextruded parcels scanner
    res = client.get("/api/v1/ids/unextruded-parcels")
    assert res.status_code == 200
    data = res.json()
    assert "total_unextruded" in data
    assert "parcels" in data

    # 2. Test single parcel extrusion if unextruded exists
    if data["total_unextruded"] > 0:
        first_ulpin = data["parcels"][0]["ulpin"]
        res_ext = client.post(
            f"/api/v1/ids/extrude-parcel/{first_ulpin}",
            json={"building_name": "Test Residency Towers", "floors": 6, "typology": "tower"}
        )
        assert res_ext.status_code == 200
        ext_data = res_ext.json()
        assert ext_data["status"] == "SUCCESS"
        assert "building" in ext_data
        bld = ext_data["building"]
        assert bld["ulpin"] == first_ulpin
        assert len(bld["units"]) > 0

        # Verify minted 3D-ULPINs
        p_bldg = parse_and_validate_3d_id(bld["proposed_3d_id"])
        assert p_bldg.is_valid is True

        for u in bld["units"]:
            p_u = parse_and_validate_3d_id(u["proposed_3d_id"])
            assert p_u.is_valid is True


def test_detailed_builder_submission_intake(authed_builder):
    """A detailed intake records a proposal and returns no decision.

    The previous version of this asserted `status in ("APPROVED",
    "UNDER_REVIEW")` and `nbc_compliance_audit.all_passed is True`, which is the
    fabrication itself: nothing in the request had been reviewed by anyone, and
    the assertion pinned the endpoint to returning an approval it had no basis
    to give.
    """
    from fastapi.testclient import TestClient
    client = authed_builder

    payload = {
        "project_name": "Sapphire Greens Towers",
        "parcel_ulpin": "20260925001302",
        # Placeholder claims. Nothing here is checked against a registry.
        "builder_rera_id": "TEST-RERA-0001",
        "municipal_sanction_no": "TEST-SANCTION-0001",
        "commencement_cert_date": "2026-08-01",
        "building_typology": "tower",
        "total_height_m": 28.0,
        "floors_above_ground": 8,
        "fsi_proposed": 1.80,
        "setback_front_m": 6.5,
        "setback_rear_m": 4.8,
        "setback_side_north_m": 4.5,
        "setback_side_south_m": 4.5,
    }

    res = client.post("/api/v1/builder/submissions/detailed", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert "submission_id" in data
    # No decision. Intake cannot approve.
    assert data["record_status"] == "PENDING_REVIEW"
    assert "APPROVED" not in data["record_status"]
    # What acceptance would mean, carried on the response.
    assert "not a government certification" in data["record_basis"].lower()

    # Threshold comparison is advisory and is not called an audit verdict.
    assert data["advisory_threshold_findings"]["all_thresholds_met"] is True
    assert "nbc_compliance_audit" not in data
    for chk in data["advisory_threshold_findings"]["checks"]:
        assert "NBC" not in chk["check"]
        assert "UDCPR" not in chk["check"]
        assert chk["met"] is True

    # Statutory identifiers come back labelled as unverified claims.
    declared = data["declared_by_submitter_not_verified"]
    assert declared["rera_id"] == "TEST-RERA-0001"
    assert "not checked against any registry" in declared["note"].lower()

    assert data["minted_3d_ulpins"]["total_minted"] > 0
    assert len(data["minted_3d_ulpins"]["units"]) > 0
    # Derived identifiers are labelled as such, not presented as allocations.
    assert "not registry" in data["minted_3d_ulpins"]["identifier_note"].lower()


def test_detailed_intake_rejects_a_parcel_with_no_geometry(authed_builder):
    """An unusable parcel is a 422, not a success reporting zero units.

    `extrude_single_parcel` raises ValueError for a ULPIN that is not in the
    registry. That was caught by a bare `except Exception: pass`, so the caller
    received 200 and "All 0 strata 3D-ULPIN units minted with ISO/IEC 7064
    check" -- a successful mint of nothing.
    """
    client = authed_builder

    payload = {
        "project_name": "Nowhere Tower",
        "parcel_ulpin": "99999999999999",
        "building_typology": "tower",
        "total_height_m": 28.0,
        "floors_above_ground": 8,
        "fsi_proposed": 1.8,
    }

    res = client.post("/api/v1/builder/submissions/detailed", json=payload)
    assert res.status_code == 422, res.text
    body = res.json()
    assert "99999999999999" in body["detail"]
    # The giveaway phrase from the old behaviour must not come back.
    assert "minted" not in res.text.lower()
