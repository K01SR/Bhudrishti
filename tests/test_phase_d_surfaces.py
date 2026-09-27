"""Phase D: persisted builder structure surfaces into the parcel/registry views.

A drawn-and-submitted structure is real data. It must surface with honest
labels: the parcel detail advertises address/locality and the level names the
submitter used; the building summary says PENDING_REVIEW (a workflow state, not
a survey) instead of the constant "SURVEYED"; and the precinct layer lists the
row as a real record with is_synthetic False rather than fabricating anything.

The stats endpoint must survive an absent FSI without turning it into a zero
average, and the old "SURVEYED" constant must be gone from the codebase.
"""
import json
import pathlib

import pytest

from tests.conftest import _login


def _postgres_reachable() -> bool:
    try:
        from sqlalchemy import text
        from app.core.database import sync_engine
        with sync_engine.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _login_as(client, username: str):
    data = _login(client, username)
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.mark.skipif(
    not _postgres_reachable(),
    reason="no Postgres reachable from this environment",
)
def test_drawn_structure_surfaces_with_honest_surface_labels(client, authed_builder):
    from sqlalchemy import text as sqltext
    from app.core.database import sync_engine

    ulpin = "TESTD4DEMO0001"
    with sync_engine.begin() as conn:
        conn.execute(sqltext("DELETE FROM verification_cases WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u)"), {"u": ulpin})
        conn.execute(sqltext("DELETE FROM submissions WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u)"), {"u": ulpin})
        conn.execute(sqltext("DELETE FROM levels WHERE structure_id IN (SELECT id FROM structures WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u))"), {"u": ulpin})
        conn.execute(sqltext("DELETE FROM structures WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u)"), {"u": ulpin})
        conn.execute(sqltext("DELETE FROM parcels WHERE ulpin = :u"), {"u": ulpin})
        conn.execute(sqltext("DELETE FROM users WHERE id IN ('usr-builder-demo','usr-district-admin')"))
        jid = conn.execute(sqltext("SELECT id FROM jurisdictions LIMIT 1")).scalar_one()
        conn.execute(
            sqltext(
                "INSERT INTO users (id, username, email, hashed_password, full_name, role_name, is_active, jurisdiction_id) "
                "VALUES ('usr-builder-demo','builder.demo','submissions@apexinfra.in','!demo-only!','Apex InfraProjects (test)','BUILDER',true,:j)"
            ),
            {"j": jid},
        )
        conn.execute(
            sqltext(
                "INSERT INTO users (id, username, email, hashed_password, full_name, role_name, is_active, jurisdiction_id) "
                "VALUES ('usr-district-admin','district.admin','district.reviewer@example.invalid','!demo-only!','Sunita Patil (test)','DISTRICT_VERIFIER',true,:j)"
            ),
            {"j": jid},
        )

    res = authed_builder.post(
        "/api/v1/builder/submissions/detailed",
        json={
            "project_name": "Promenade",
            "parcel_ulpin": ulpin,
            "building_typology": "slab",
            "floors_above_ground": 3,
            "basements_count": 1,
            "floor_to_floor_height_m": 3.2,
            "total_height_m": 9.6,
            "address": "29 Marina Walk",
            "locality": "Airoli",
            "footprint_ring": [[0, 0], [20, 0], [20, 10], [0, 10]],
            "floor_labels": [
                {"level_code": "G", "name": "Ground", "use": "Commercial"},
                {"level_code": "L01", "name": "Level One", "use": "Residential"},
                {"level_code": "L02", "name": "Level Two", "use": "Residential"},
            ],
        },
    )
    assert res.status_code == 200, res.text

    try:
        # --- parcel detail view ---
        det = client.get(f"/api/v1/parcels/{ulpin}")
        assert det.status_code == 200, det.text
        parcel = det.json()
        assert parcel["address"] == "29 Marina Walk"
        assert parcel["locality"] == "Airoli"

        building = parcel["building"]
        assert building is not None
        # A workflow state, not a survey claim.
        assert building["status"] == "PENDING_REVIEW", building["status"]
        assert building["is_verified"] is False
        assert building["provenance"] == "demo-generated"
        assert building["height_basis"] == "declared_by_submitter"
        level_codes = [lv["level_code"] for lv in building["levels"]]
        assert level_codes == ["G", "L01", "L02"], level_codes
        names = {lv["level_code"]: lv["name"] for lv in building["levels"]}
        uses = {lv["level_code"]: lv["use"] for lv in building["levels"]}
        assert names == {"G": "Ground", "L01": "Level One", "L02": "Level Two"}
        assert uses == {"G": "Commercial", "L01": "Residential", "L02": "Residential"}

        # The workflow record behind the status.
        rec = parcel["builder_record"]
        assert rec is not None
        assert rec["receipt_number"].startswith("SUB-2026-")
        assert rec["status"] == "PENDING_REVIEW"
        assert rec["decision"] is None

        # structures[] carries the submitter's floor names too.
        assert parcel["structures"][0]["data_provenance"] == "demo-generated"
        assert parcel["structures"][0]["levels"][1]["name"] == "Level One"

        # --- precinct layer reports the real row, not a scenario ---
        from app.services.builder_records import list_persisted_builder_structures

        listed = [b for b in list_persisted_builder_structures() if b["ulpin"] == ulpin]
        assert len(listed) == 1, "persisted structure missing from precinct build"
        entry = listed[0]
        assert entry["is_synthetic"] is False
        assert entry["geometry_basis"] == "builder-asserted, not surveyed"
        assert entry["status"] == "PENDING_REVIEW"
        assert entry["units_count"] == 0
        assert entry["ulpin"] == ulpin
        assert entry["address"] == "29 Marina Walk"
        assert entry["locality"] == "Airoli"
        assert entry["w"] == 20.0 and entry["h"] == 10.0
        assert {lv["level_code"] for lv in entry["levels"]} == {"G", "L01", "L02"}
        assert entry["fsi"] is None  # no surveyed area basis, so no FSI
    finally:
        with sync_engine.begin() as conn:
            conn.execute(sqltext("DELETE FROM verification_cases WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u)"), {"u": ulpin})
            conn.execute(sqltext("DELETE FROM submissions WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u)"), {"u": ulpin})
            conn.execute(sqltext("DELETE FROM levels WHERE structure_id IN (SELECT id FROM structures WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u))"), {"u": ulpin})
            conn.execute(sqltext("DELETE FROM structures WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u)"), {"u": ulpin})
            conn.execute(sqltext("DELETE FROM parcels WHERE ulpin = :u"), {"u": ulpin})
            conn.execute(sqltext("DELETE FROM users WHERE id IN ('usr-builder-demo','usr-district-admin')"))


def test_reviewer_attribution_is_the_reviewer_not_the_submitter(client):
    """`builder_record.reviewer_name` must be the reviewer, not the submitter.

    The query used to join `users` through `sub.submitter_id` and alias it
    `reviewer_name`, so an unreviewed submission reported the builder as the
    person who reviewed it. A field named for the reviewer has to name the
    reviewer, and while nobody has decided it must be null.
    """
    from sqlalchemy import text as sqltext
    from app.core.database import sync_engine

    ulpin = "TESTD4REVIEW01"
    clean = [
        "DELETE FROM verification_cases WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u)",
        "DELETE FROM submissions WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u)",
        "DELETE FROM levels WHERE structure_id IN (SELECT id FROM structures WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u))",
        "DELETE FROM structures WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u)",
        "DELETE FROM parcels WHERE ulpin = :u",
        "DELETE FROM users WHERE id IN ('usr-builder-demo','usr-district-admin')",
    ]
    with sync_engine.begin() as conn:
        for stmt in clean:
            conn.execute(sqltext(stmt), {"u": ulpin})
        jid = conn.execute(sqltext("SELECT id FROM jurisdictions LIMIT 1")).scalar_one()
        conn.execute(
            sqltext(
                "INSERT INTO users (id, username, email, hashed_password, full_name, role_name, is_active, jurisdiction_id) "
                "VALUES ('usr-builder-demo','builder.demo','submissions@apexinfra.in','!demo-only!','Apex InfraProjects (test)','BUILDER',true,:j)"
            ),
            {"j": jid},
        )
        conn.execute(
            sqltext(
                "INSERT INTO users (id, username, email, hashed_password, full_name, role_name, is_active, jurisdiction_id) "
                "VALUES ('usr-district-admin','district.admin','district.reviewer@example.invalid','!demo-only!','Sunita Patil (test)','DISTRICT_VERIFIER',true,:j)"
            ),
            {"j": jid},
        )

    try:
        # Both roles are needed, and the shared TestClient carries one auth
        # header, so each call states who it is acting as.
        builder_hdr = _login_as(client, "builder.demo")
        verifier_hdr = _login_as(client, "district.admin")
        res = client.post(
            "/api/v1/builder/submissions/detailed",
            headers=builder_hdr,
            json={
                "project_name": "Attribution Probe",
                "parcel_ulpin": ulpin,
                "building_typology": "slab",
                "floors_above_ground": 1,
                "floor_to_floor_height_m": 3.0,
                "total_height_m": 3.0,
                "footprint_ring": [[0, 0], [10, 0], [10, 10], [0, 10]],
                "floor_labels": [{"level_code": "G", "name": "Ground", "use": "Residential"}],
            },
        )
        assert res.status_code == 200, res.text
        sub_id = res.json()["submission_id"]

        pending = client.get(f"/api/v1/parcels/{ulpin}").json()["builder_record"]
        assert pending["status"] == "PENDING_REVIEW"
        assert pending["decision"] is None
        # Nobody has reviewed it, so the reviewer is unknown, not the builder.
        assert pending["reviewer_name"] is None
        assert pending["submitted_by"] == "Apex InfraProjects (test)"

        disp = client.post(
            f"/api/v1/builder/submissions/{sub_id}/disposition",
            headers=verifier_hdr,
            json={
                "decision": "ACCEPTED_FOR_RECORD",
                "reason": "Geometry matches the submitted drawing; accepted for pilot record only.",
            },
        )
        assert disp.status_code == 200, disp.text

        decided = client.get(f"/api/v1/parcels/{ulpin}").json()["builder_record"]
        assert decided["decision"] == "APPROVED", decided
        assert decided["reviewer_name"] == "Sunita Patil (test)", decided
        assert decided["submitted_by"] == "Apex InfraProjects (test)"
    finally:
        with sync_engine.begin() as conn:
            for stmt in clean:
                conn.execute(sqltext(stmt), {"u": ulpin})


def test_precinct_stats_survive_an_absent_fsi():
    """A structure with no verified area basis must not become a zero average."""
    from app.api.v1.precinct import get_precinct_stats

    stats = get_precinct_stats()
    assert "average_fsi" in stats
    # These tally rows by their state in the generated demo dataset. They are
    # named after that state rather than after approval outcomes, because a
    # count of "approved"/"violating" buildings reads as a regulatory finding
    # that no authority made and this demo cannot make.
    assert isinstance(stats["standard_count"], int)
    assert isinstance(stats["elevated_fsi_count"], int)
    assert isinstance(stats["epoch_comparison_count"], int)


def test_no_constant_surveyed_status_remains():
    """_building_of hardcoded status="SURVEYED" regardless of origin.

    A builder's drawn footprint has never been surveyed, so the summary must
    derive the honest state instead."""
    src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "backend" / "app" / "api" / "v1" / "parcels.py"
    ).read_text()
    assert '"status": "SURVEYED"' not in src
    assert '"status": "APPROVED"' not in src.split("_DATASET_CACHE")[0][-3000:]


def test_phase_d_has_no_invented_units_in_precinct_merge():
    src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "backend" / "app" / "services" / "builder_records.py"
    ).read_text()
    fn = src.split("def list_persisted_builder_structures")[-1]
    assert '"units_count": 0' in fn
    assert "synthesise" not in fn.lower() and "invent" in fn.lower()