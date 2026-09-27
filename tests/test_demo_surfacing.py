"""Regression tests for demo-only data leaking into default (real) responses.

The purge removed the 45,489 generated rows from national_parcels but left the
45,489 rows in national_twins, labelled ``modelled_from_synthetic_parcel``. An
API-level gate is not sufficient on its own: the vector tile pyramid and the
admin rollup endpoints read those tables directly, and an atlas tile is
indistinguishable from a survey boundary once it is drawn.

These tests pin the layers and aggregates behind ENABLE_DEMO_MODE so a re-seed of
the generated grid cannot quietly repopulate a default deployment.
"""
import json
import pathlib

import pytest

from frontend_source import frontend_src_root

from app.core.demo_gate import demo_mode_enabled
from app.tiles import tiles


@pytest.fixture
def demo_off(monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "0")
    assert not demo_mode_enabled()


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    assert demo_mode_enabled()


def test_admin_boundaries_always_available(demo_off):
    """admin_boundaries is genuine and must survive the gate."""
    available = tiles._available_layers()
    assert {"state", "district", "taluka", "village"} <= set(available)


def test_synthetic_layers_hidden_when_demo_off(demo_off):
    available = tiles._available_layers()
    assert "parcel" not in available, "national_parcels is synthetic and purged"
    assert "twin" not in available, "national_twins geometry is synthetic"


def test_synthetic_layers_present_when_demo_on(demo_on):
    available = tiles._available_layers()
    assert {"parcel", "twin"} <= set(available)


def test_requested_layers_cannot_smuggle_a_gated_layer(demo_off):
    """A client asking for 'twin' by name must not get it."""
    available = tiles._available_layers()
    requested = [L.strip() for L in "state,twin,parcel".split(",") if L.strip() in available]
    assert requested == ["state"]


@pytest.mark.anyio
async def test_tile_requesting_only_a_gated_layer_is_empty(demo_off):
    """Asking solely for 'twin' must not substitute the default layer set.

    The gate originally filtered the requested list and then fell back to
    `list(available)` when the result was empty, so a client asking only for a
    withheld layer silently received the whole admin pyramid instead of nothing.
    """
    import asyncio

    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(
        None, lambda: asyncio.run(tiles.get_tile(5, 20, 12, "twin"))
    )
    assert resp.status_code == 200
    assert len(resp.body) <= 32, "expected an empty gzip payload, not a substituted layer set"


@pytest.mark.anyio
async def test_tile_with_unrecognised_layer_falls_back_to_default(demo_off):
    """Garbage input still falls back to the default layer set."""
    import asyncio

    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(
        None, lambda: asyncio.run(tiles.get_tile(5, 20, 12, "not-a-layer"))
    )
    assert resp.status_code == 200


def test_meta_advertises_unavailable_layers_explicitly(demo_off):
    """The gate must be legible to a client, not silently drop layers."""
    import asyncio

    meta = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        tiles.get_tile_meta()
    )
    assert "twin" not in meta["layers"]
    assert "parcel" not in meta["layers"]
    # ...but /meta says they exist and why they are absent.
    assert set(meta["unavailable_layers"]) == {"parcel", "twin"}
    for spec in meta["unavailable_layers"].values():
        assert "ENABLE_DEMO_MODE" in spec["reason"]


def test_default_layer_listing_excludes_synthetic_tables(demo_off):
    """The endpoint default must not resolve to a synthetic layer set."""
    available = tiles._available_layers()
    assert all(
        tiles.LAYERS[name]["table"] not in {"national_parcels", "national_twins"}
        for name in available
    )


def test_deployment_endpoint_reports_the_real_gate(client):
    """
    The UI rendered a "Demo dataset" marker from a hardcoded string in ten
    places, so it appeared on deployments serving no generated data. The flag
    has to be readable from the API for the UI to label itself honestly.
    """
    res = client.get("/api/v1/system/deployment")
    assert res.status_code == 200
    body = res.json()

    # conftest opens the demo gate suite-wide, so it must read as on here.
    assert body["demo_mode"] is True
    assert body["synthetic_data_served"] is True
    assert body["signing_key"] == "published demonstration keypair"
    assert "invented" in body["note"]


def test_deployment_endpoint_is_honest_with_the_gate_shut(client, monkeypatch):
    """With the gate shut the endpoint must not claim to serve demo data."""
    monkeypatch.setenv("ENABLE_DEMO_MODE", "0")
    res = client.get("/api/v1/system/deployment")
    assert res.status_code == 200
    body = res.json()

    assert body["demo_mode"] is False
    assert body["synthetic_data_served"] is False
    assert "Generated demonstration data is being served" not in body["note"]
    assert "no generated demonstration data" in body["note"].lower()


def test_deployment_flag_matches_the_gate_that_serves_the_data(client, monkeypatch):
    """
    Guards against the flag and the actual gate drifting apart, which would let
    the UI claim demo data is or is not present independently of what the API
    returns.
    """
    import os

    for value, expected in (("1", True), ("0", False)):
        monkeypatch.setenv("ENABLE_DEMO_MODE", value)
        reported = client.get("/api/v1/system/deployment").json()["demo_mode"]
        actual = os.getenv("ENABLE_DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
        assert reported is expected
        assert reported is actual


DEMO_ULPIN_LITERAL = "12345678901234"

# The landing page is frozen and still contains the literal in its own copy and
# placeholder text. It is excluded from the gate deliberately, not overlooked.


def test_demo_ulpin_is_defined_in_exactly_one_place():
    """
    The demonstration parcel identifier was copied as a bare literal into
    nineteen app files: thirty-nine occurrences of a number that is not a real
    ULPIN. A reader could not tell an invented showcase identifier from a
    registry record without opening every call site, and changing it meant
    finding all of them. It is now defined once in frontend/src/constants.ts.
    """
    root = frontend_src_root()
    expected = root / "constants.ts"

    from frontend_source import executable_source, frontend_files

    landing = [root / "pages" / "LandingPage.tsx", root / "components" / "landing"]
    files = frontend_files(extra_excludes=landing)
    assert files, "no frontend sources found; the checks below would be vacuous"
    holders = [p for p in files if DEMO_ULPIN_LITERAL in executable_source(p)]

    assert holders == [expected], (
        "the literal belongs only in constants.ts, found in executable code of: "
        f"{[str(p) for p in holders]}"
    )


def test_demo_ulpin_constant_is_labelled_as_a_prototype_identifier():
    """
    Guards the label, not just the location. The constant must not describe
    itself as issued or official, since a registry has issued nothing here.
    """
    constants = (
        pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src" / "constants.ts"
    ).read_text()
    assert "export const DEMO_ULPIN" in constants
    assert "not a ULPIN" in constants
    for claim in ("official ULPIN", "issued ULPIN", "registry ULPIN"):
        assert claim not in constants, f"constants.ts still calls it {claim!r}"


def test_ui_does_not_present_the_demo_ulpin_as_indias_official_identifier():
    """
    The guided-tour script told a presenter to open by clarifying that the app
    "does NOT replace India's official 14-character ULPIN (12345678901234)",
    which introduced the number as the official one.
    """
    tour = (
        pathlib.Path(__file__).resolve().parents[1]
        / "frontend" / "src" / "components" / "modals" / "GuidedTourModal.tsx"
    ).read_text()
    assert "India's official 14-character ULPIN" not in tour
    assert "prototype parcel identifier" in tour


class _RecordingConn:
    """Stands in for an async SQLAlchemy connection and records the SQL sent."""

    def __init__(self, sink):
        self._sink = sink

    async def execute(self, statement, *args, **kwargs):
        self._sink.append(str(statement))
        return _EmptyResult()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _EmptyResult:
    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _RecordingEngine:
    def __init__(self):
        self.statements = []

    def connect(self):
        return _RecordingConn(self.statements)


@pytest.mark.anyio
async def test_search_never_queries_the_generated_tables_when_demo_off(demo_off):
    """/search read national_parcels and national_twins with no gate at all.

    Both tables are written only by app/scripts/seed_mumbai_metropolitan.py,
    and national_twins still holds 45,489 generated rows after the purge. The
    gate existed elsewhere in the app, so shutting it left these two queries
    live and a real-data-only deployment returned invented parcels and
    buildings from its main search box.
    """
    from app.api.v1 import search as search_module

    engine = _RecordingEngine()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(search_module, "async_engine", engine)
        await search_module.search("Airoli", mode="records", limit=10)

    sql = "\n".join(engine.statements).lower()
    assert "national_twins" not in sql
    assert "national_parcels" not in sql
    # The grid-synthesised TALUKA/VILLAGE subdivisions are generated too.
    assert "'synthetic'" in sql, "expected the synthetic-boundary filter to be applied"


@pytest.mark.anyio
async def test_search_still_queries_generated_tables_when_demo_on(demo_on):
    """The gate must hide generated rows, not permanently disable the demo."""
    from app.api.v1 import search as search_module

    engine = _RecordingEngine()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(search_module, "async_engine", engine)
        await search_module.search("Airoli", mode="records", limit=10)

    sql = "\n".join(engine.statements).lower()
    assert "national_twins" in sql
    assert "'synthetic'" not in sql


def test_property_card_does_not_resolve_a_twin_when_demo_off(demo_off):
    """/exports/property-card/{ulpin} fell back to national_twins ungated.

    A ULPIN that matched a generated twin got an invented building extruded on
    its property card, whatever the gate was set to.
    """
    from app.api.v1 import exports as exports_module

    touched = []

    def _session_factory():
        touched.append(True)
        raise AssertionError("national_twins must not be queried while the gate is shut")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(exports_module, "SyncSessionLocal", _session_factory)
        exports_module._resolve_property_data("EFG49POQQEF0OH")

    assert not touched, "the national_twins lookup ran with the gate shut"


def test_property_card_invents_nothing_for_an_unknown_ulpin(demo_off):
    """The worst leak: an unknown ULPIN got a fabricated property card.

    `_resolve_property_data` had a third step that ran for *any* string --
    including a typo -- and invented a building: 6 floors, 21.0 m, a 900 m2
    plot, fsi_status "PASS", a "CTS-" survey number, a fixed polygon at
    145.0/145.0, and 24 units each holding a "Registered Allottee" with
    encumbrance_status CLEAR. `GET /exports/pdf/property-card/{ulpin}` then
    rendered that as a property card.

    The Makefile smoke target hits this route, so it was not a dead path.
    """
    from app.api.v1 import exports as exports_module

    assert exports_module._resolve_property_data("TOTALLY-MADE-UP-0001") is None
    assert exports_module._resolve_property_data("3D-ULPIN-ZZIUOTK4MJZFMT") is None


def test_property_card_404s_instead_of_inventing_when_demo_off(demo_off):
    """The endpoints must answer 'not published', not crash or fabricate."""
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from app.main import app

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ENABLE_DEMO_MODE", "0")
        client = TestClient(app)
        for path in ("/api/v1/exports/pdf/property-card/NOT-A-REAL-ULPIN",
                     "/api/v1/exports/latex/property-card/NOT-A-REAL-ULPIN"):
            resp = client.get(path)
            assert resp.status_code == 404, f"{path} -> {resp.status_code}"
            assert "real dataset" in resp.json()["detail"]


def test_validation_run_refuses_rather_than_crashing_when_demo_off(demo_off):
    """/validation/run 500'd once the gate was shut.

    It ran TopologyQAEngine against `empty_dataset()`, which hands back {} for
    hero_parcel, and the engine calls
    `shape(parcel_data.get("polygon_geojson", {}))` -- so shape() got None and
    raised AttributeError. A 500 reads as an outage; the honest answer is 503,
    because there is no dataset to validate. It also snapshotted the dataset at
    import, the same mistake Ask Map made.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ENABLE_DEMO_MODE", "0")
        client = TestClient(app)
        resp = client.get("/api/v1/validation/run")

    assert resp.status_code == 503
    assert resp.headers.get("X-Demo-Mode") == "disabled"
    assert "demonstration data is disabled" in resp.json()["detail"].lower()


def test_validation_rule_catalog_is_not_presented_as_evidence_of_a_run(demo_off):
    """A description of a rule is not a result. The catalogue stays available."""
    from fastapi.testclient import TestClient
    from app.main import app

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ENABLE_DEMO_MODE", "0")
        client = TestClient(app)
        resp = client.get("/api/v1/validation/rules")

    assert resp.status_code == 200
    # 16, not 12: R013-R016 (title and ownership conflict) joined the catalogue
    # when the engine began running them, and a catalogue missing rules the engine
    # runs would describe a different engine than the one that exists.
    assert len(resp.json()) == 16


def test_integrity_board_refuses_rather_than_scoring_generated_parcels(demo_off):
    """/integrity/* scored a hardcoded demo precinct and hardcoded verdicts.

    Every route read `_DATASET`, the snapshot of the Airoli demo precinct taken
    at import, and answered with an integrity band per parcel. Worse, the hero
    parcel's validation factor carried a literal compliance claim -- "11/12
    rules passed; R009 subsurface clash (PIPE-DRAIN-01 x METRO-LINE-2A) open"
    -- that nothing computed. That rule count had already moved to 16, so the
    number was stale as well as invented.

    With the gate shut there is no dataset to score, so the honest answer is 503
    instead of a confident score for a parcel that does not exist.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ENABLE_DEMO_MODE", "0")
        client = TestClient(app)
        responses = [
            client.get("/api/v1/integrity/overview"),
            client.get("/api/v1/integrity/duplicates"),
            client.get("/api/v1/integrity/properties/12345678901234"),
        ]

    for resp in responses:
        assert resp.status_code == 503, (resp.request.url, resp.status_code, resp.text)
        assert resp.headers.get("X-Demo-Mode") == "disabled"


def test_integrity_never_claims_a_rule_pass_count_it_did_not_compute(demo_on):
    """No route may assert a pass count or a named clash as a result.

    The hero factor used to read "11/12 rules passed; R009 subsurface clash
    (PIPE-DRAIN-01 x METRO-LINE-2A) open" as a literal. A rule catalogue is
    available evidence of what would be checked; a pass count and a named clash
    are a verdict, and this module does not run the engine to produce one.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ENABLE_DEMO_MODE", "1")
        client = TestClient(app)
        payload = client.get("/api/v1/integrity/properties/12345678901234").json()

    # Scoped to the validation factor. The demo audit *timeline* legitimately
    # carries historical log entries ("passed: 11; failed: 1; issue: R009"),
    # which is recorded demo content rather than a live verdict; what must not
    # happen is the integrity score asserting a pass count it never computed.
    factors = {f["key"]: f for f in payload["factors"]}
    validation = json.dumps(factors["validation"])
    assert "rules passed" not in validation, validation
    assert "11/12" not in validation, validation
    assert "R009" not in validation, validation
    assert "R016" in factors["validation"]["label"], validation


# Every route group that answers with generated Airoli content must refuse while
# the gate is shut. These four routers loaded `load_demo_dataset()` at import but
# never declared a gate, so with ENABLE_DEMO_MODE=0 they still returned 200 with
# fabricated records: a named party and a mortgage amount under /rights/summary,
# a hardcoded hero ULPIN under /changes/compare, and placeholder evidence
# streams under /evidence.
GENERATED_CONTENT_ROUTES = [
    "/api/v1/changes/compare",
    "/api/v1/evidence/",
    "/api/v1/evidence/EV-01",
    "/api/v1/rights/summary",
    "/api/v1/qr/verify/xyz",
    "/api/v1/qr/certificate/xyz",
    "/api/v1/qr/ledger/xyz",
    "/api/v1/integrity/overview",
    "/api/v1/integrity/duplicates",
    "/api/v1/integrity/properties/12345678901234",
]


@pytest.mark.parametrize("path", GENERATED_CONTENT_ROUTES)
def test_generated_content_routes_refuse_when_demo_off(path):
    """No route may answer 200 with generated content while the gate is shut."""
    from fastapi.testclient import TestClient
    from app.main import app

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ENABLE_DEMO_MODE", "0")
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(path)

    assert resp.status_code == 503, (path, resp.status_code, resp.text[:200])
    assert resp.headers.get("X-Demo-Mode") == "disabled", path


@pytest.mark.parametrize("path", GENERATED_CONTENT_ROUTES)
def test_generated_content_routes_still_work_in_a_demo_run(path):
    """Gating must not break the demonstration run it is meant to permit."""
    from fastapi.testclient import TestClient
    from app.main import app

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ENABLE_DEMO_MODE", "1")
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(path)

    assert resp.status_code == 200, (path, resp.status_code, resp.text[:200])


def test_rights_summary_does_not_serve_a_named_party_and_a_mortgage_when_demo_off(demo_off):
    """/rights/summary was a literal dict of invented encumbrances.

    It named two private individuals as 100% owners of unit 201 and attached an
    ₹85,00,000 State Bank of India mortgage to them. Nothing derived that from a
    deed; it was hardcoded next to a disclaimer, and the disclaimer does not
    travel with the values once a client reads one field.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ENABLE_DEMO_MODE", "0")
        client = TestClient(app)
        resp = client.get("/api/v1/rights/summary")

    assert resp.status_code == 503
    blob = resp.text
    for leaked in ["Karan Malhotra", "Priya Malhotra", "85,00,000", "State Bank of India"]:
        assert leaked not in blob, leaked


def test_the_rendering_legend_is_not_gated(demo_on):
    """/rights/color-modes is configuration, not a claim about a parcel.

    It returns colour keys whose labels already read "In Demo" and asserts
    nothing about any real record, so it stays available in a real-only
    deployment. Gating it would remove the viewer legend without hiding
    anything false.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ENABLE_DEMO_MODE", "0")
        client = TestClient(app)
        resp = client.get("/api/v1/rights/color-modes")

    assert resp.status_code == 200
    assert resp.json()["modes"]


def test_administrative_tile_layers_never_draw_a_synthetic_boundary():
    """The atlas must not render a seeded rectangle as an administrative area.

    `admin_boundaries` is not one provenance. Alongside 771 genuine
    geoBoundaries rows (36 STATE, 735 DISTRICT) it holds 11,385 synthetic
    VILLAGE and 2,935 synthetic TALUKA rows written by
    seed_mumbai_metropolitan.py, plus 32 rows with no source at all.

    The tile layers selected on `level` alone, so with the demo gate shut the
    map still drew 14,320 invented boundaries. This is worse than a JSON leak:
    a rendered polygon reads as surveyed no matter what the API says. Each
    administrative layer is now scoped to rows naming a real provider.
    """
    from app.tiles import tiles

    genuine = tiles._GENUINE_BOUNDARY
    for name in ("state", "district", "taluka", "village"):
        where = tiles.LAYERS[name]["where"]
        assert "synthetic" in where, (name, where)
        assert "source IS NOT NULL" in where, (name, where)
        assert where.startswith("level="), (name, where)

    # The filter has to be applied to every admin layer, not just the two that
    # currently happen to hold only genuine rows.
    assert "synthetic" not in tiles.LAYERS["parcel"]["where"]
    assert "synthetic" not in tiles.LAYERS["twin"]["where"]


def test_synthetic_boundary_rows_are_not_reachable_through_any_tile_layer():
    """No LAYERS entry may select a table without a provenance predicate."""
    from app.tiles import tiles

    for name, spec in tiles.LAYERS.items():
        where = spec["where"]
        if spec["table"] == "admin_boundaries":
            assert "source" in where, (name, where)
        else:
            # Generated tables are refused wholesale by the demo-only gate.
            assert name in tiles._DEMO_ONLY_LAYERS, (name, spec["table"])
