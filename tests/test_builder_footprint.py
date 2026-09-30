"""Phase C2: a drawn footprint becomes real geometry, labelled as asserted.

The 2D parcel picker + polygon editor in the builder studio produce a
footprint in local metres. That ring, an address, a locality and per-floor
names/uses travel to /detail, where they are persisted as real Parcel +
Structure + Level rows. The response carries "builder-asserted, not surveyed"
because the geometry is exactly as drawn: nothing confirms it but the submitter.

The random-roll and fabricated-default gates from stage 2.5 continue to hold:
a footprint never invents a survey number or an area, and never fabricates
units that nobody subdivided.
"""
import pathlib

import pytest

from tests.conftest import _login


def _login_as(client, username: str):
    data = _login(client, username)
    return {"Authorization": f"Bearer {data['access_token']}"}


def _postgres_reachable() -> bool:
    try:
        from sqlalchemy import text
        from app.core.database import sync_engine
        with sync_engine.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _postgres_reachable(),
    reason="no Postgres reachable from this environment",
)
def test_drawn_footprint_persists_parcel_structure_and_levels(client, authed_builder):
    """Submitting a drawn ring lands real rows with submitter labels."""
    from sqlalchemy import text as sqltext
    from sqlalchemy import select
    from app.core.database import sync_engine, AsyncSessionLocal
    from app.models.cadastre import Parcel, Structure, Level

    ulpin = "TESTC2DEMO0001"
    with sync_engine.begin() as conn:
        conn.execute(sqltext("DELETE FROM levels WHERE structure_id IN (SELECT id FROM structures WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u))"), {"u": ulpin})
        conn.execute(sqltext("DELETE FROM structures WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u)"), {"u": ulpin})
        conn.execute(sqltext("DELETE FROM parcels WHERE ulpin = :u"), {"u": ulpin})

    payload = {
        "project_name": "Riverside Block",
        "parcel_ulpin": ulpin,
        "building_typology": "slab",
        "floors_above_ground": 3,
        "basements_count": 1,
        "floor_to_floor_height_m": 3.2,
        "total_height_m": 9.6,
        "fsi_proposed": 1.4,
        "setback_front_m": 6.5,
        "setback_side_north_m": 4.5,
        "setback_side_south_m": 4.5,
        "address": "Plot 14, Riverside Avenue",
        "locality": "Airoli",
        "footprint_ring": [[0, 0], [24, 0], [24, 12], [0, 12]],
        "floor_labels": [
            {"level_code": "G", "name": "Ground", "use": "Commercial"},
            {"level_code": "L01", "name": "Level One", "use": "Residential"},
            {"level_code": "L02", "name": "Level Two", "use": "Residential"},
        ],
    }
    try:
        res = authed_builder.post("/api/v1/builder/submissions/detailed", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()

        geo = data["asserted_geometry"]
        assert "builder-asserted, not surveyed" in geo["basis"]
        assert geo["footprint_vertex_count"] == 4
        assert geo["persistence"]["persisted"] is True, geo["persistence"]
        assert geo["structure_code"]

        async def check():
            async with AsyncSessionLocal() as db:
                parcel = (
                    await db.execute(select(Parcel).where(Parcel.ulpin == ulpin))
                ).scalar_one()
                assert parcel.address == "Plot 14, Riverside Avenue"
                assert parcel.locality == "Airoli"
                assert parcel.survey_number is None
                assert parcel.data_provenance == "demo-generated"
                assert parcel.provenance_authoritative is False
                assert parcel.document_area_m2 is not None
                assert parcel.calculated_area_m2 is not None

                structure = (
                    await db.execute(
                        select(Structure).where(Structure.parcel_id == parcel.id)
                    )
                ).scalar_one()
                assert structure.name == "Riverside Block"
                assert structure.height_basis == "declared_by_submitter"
                assert structure.is_verified is False
                assert structure.floors_count == 3

                levels = (
                    await db.execute(
                        select(Level).where(Level.structure_id == structure.id).order_by(Level.floor_number)
                    )
                ).scalars().all()
                assert [lv.level_code for lv in levels] == ["G", "L01", "L02"]
                assert [lv.name for lv in levels] == ["Ground", "Level One", "Level Two"]
                assert [lv.use for lv in levels] == ["Commercial", "Residential", "Residential"]

        import asyncio

        asyncio.run(check())
    finally:
        with sync_engine.begin() as conn:
            conn.execute(sqltext("DELETE FROM levels WHERE structure_id IN (SELECT id FROM structures WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u))"), {"u": ulpin})
            conn.execute(
                sqltext("DELETE FROM structures WHERE parcel_id IN (SELECT id FROM parcels WHERE ulpin = :u)"),
                {"u": ulpin},
            )
            conn.execute(sqltext("DELETE FROM parcels WHERE ulpin = :u"), {"u": ulpin})


def test_footprint_ring_with_fewer_than_three_vertices_is_rejected(authed_builder):
    payload = {
        "project_name": "Degenerate Ring",
        "parcel_ulpin": "202609250001",
        "footprint_ring": [[0, 0], [5, 0]],
    }
    res = authed_builder.post("/api/v1/builder/submissions/detailed", json=payload)
    assert res.status_code == 422, res.text
    assert "at least 3 vertices" in res.json()["detail"]


def test_no_fabricated_survey_numbers_or_areas_remain_in_the_parcel_api():
    """The national-registry fallback used `p_s or 'CTS-<dl>'` and
    `if a_m2 else 1000.0` -- an invented survey number and an invented area
    printed for a parcel the database did not measure."""
    from frontend_source import executable_source  # noqa: manual path

    import ast

    src = pathlib.Path(
        pathlib.Path(__file__).resolve().parents[1] / "backend" / "app" / "api" / "v1" / "parcels.py"
    ).read_text()
    tree = ast.parse(src)
    literals = {
        str(n.value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and "CTS-" in str(n.value)
    }
    assert not literals, f"CTS- fabrication remains: {literals}"
    assert "1000.0" not in src.split("_DATASET_CACHE")[0][-2000:]


def test_drawn_footprint_never_creates_units():
    """The footprint path writes levels, not units: a unit is a subdivision
    nobody subdivided. The minted identifiers stay derived strings only."""
    src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "backend" / "app" / "services" / "builder_records.py"
    ).read_text()
    # persist_builder_structure imports Parcel/Structure/Level, never Unit.
    assert "from app.models.cadastre import Parcel, Structure, Level" in src
    assert "Unit" not in src.split("persist_builder_structure")[-1].split("persist_submission_row")[0]