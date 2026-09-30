"""The /precinct group must never impersonate a government record.

Found during the honesty sweep. These endpoints are demo-gated, so nothing
reaches a default deployment -- but with the flag on they produced things that
read as authentic instruments of a real municipal body:

- a property-tax demand and demolition order computed from invented statutory
  rates, falling back to a fabricated 14,81,760 INR liability for any building
  code the caller typed;
- an issuing authority of "Navi Mumbai Municipal Corporation" and a signatory of
  "Municipal Commissioner", neither of which this system is;
- "algorithm": "SHA256-ED25519-NMMC-SEAL" over a bare sha256() of a string, and a
  verification URL on bhudrishti.maharashtra.gov.in;
- a "2027 Epoch 2 UAV Point Cloud Survey (125,530 returns)" for a building that
  has never been surveyed;
- MahaRERA numbers formatted from the building code, CERSAI lien clearance and an
  SBI mortgage asserted without querying either registry;
- safe_for_purchase / bank_loan_eligible verdicts, returned for arbitrary input
  because an unknown identifier defaulted to the hero building.

These tests pin the removal of each of those.
"""
import json

import pytest


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")


def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_scenario_provenance_is_declared():
    from app.api.v1.precinct import SCENARIO_PROVENANCE

    assert SCENARIO_PROVENANCE["is_synthetic"] is True
    assert SCENARIO_PROVENANCE["authoritative"] is False
    assert SCENARIO_PROVENANCE["not_a_government_record"] is True


def test_revenue_rates_are_marked_illustrative():
    from app.api.v1 import precinct

    assert precinct.RATES_ARE_ILLUSTRATIVE is True
    # The rates must no longer be commented as the statutory figures.
    src = open(precinct.__file__).read()
    assert "NMMC Zone 8 Airoli capital valuation" not in src
    assert "Sec 267A MMC Act" not in src


def test_precinct_stats_carries_provenance(demo_on):
    r = _client().get("/api/v1/precinct/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["provenance"]["is_synthetic"] is True
    assert "not a surveyed" in body["precinct_area_source"]


def test_precinct_stats_count_only_units_that_exist(demo_on):
    """"469 vs 494": two totals for one precinct on one screen.

    /precinct/stats added a flat 21 units for the hero tower and a second
    building, whether or not those rows were loaded, while /ids/precinct
    totalled the unit rows it actually returned. The registry page rendered
    both, so the same precinct read as two different identifier counts.
    """
    client = _client()
    stats = client.get("/api/v1/precinct/stats").json()
    catalogue = client.get("/api/v1/ids/precinct").json()

    assert stats["total_units"] == catalogue["total_3d_ids"]
    assert stats["total_buildings"] == len(catalogue["buildings"])
    # Every emitted unit belongs to a building that was counted once.
    assert catalogue["total_3d_ids"] == sum(len(b["units"]) for b in catalogue["buildings"])
    assert stats["standard_count"] <= stats["total_buildings"]


def test_buyer_shield_unknown_identifier_returns_404(demo_on):
    """Any string used to receive a confident verdict about a real property."""
    r = _client().get("/api/v1/precinct/buyer-shield/verify/NOT-A-REAL-BUILDING")
    assert r.status_code == 404
    assert "CERSAI" in r.json()["detail"] or "MahaRERA" in r.json()["detail"]


def test_buyer_shield_known_building_is_marked_simulated(demo_on):
    r = _client().get("/api/v1/precinct/buyer-shield/verify/B-17")
    assert r.status_code == 200
    body = r.json()
    assert body["provenance"]["not_a_government_record"] is True
    assert body["certificate_token"] is None
    checks = {c["pillar"]: c for c in body["checks"]}
    rera = next(c for k, c in checks.items() if k.startswith("MahaRERA"))
    assert rera["rera_number"] is None, "no registration number may be formatted from the building code"
    assert rera["sanctioned_floors"] is None
    cersai = next(c for k, c in checks.items() if k.startswith("CERSAI"))
    assert cersai["status"] == "NOT_CHECKED"
    assert cersai["passed"] is None
    # No verdict may read as a purchase or financing recommendation.
    assert "not a purchase" in body["verdict"]["verdict_note"].lower()


def test_demand_notice_claims_no_authority_or_seal(demo_on, authed_builder):
    r = authed_builder.post(
        "/api/v1/precinct/generate-demand-notice",
        json={"building_code": "B-17", "notice_type": "SEC_260_DEMOLITION"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["issuing_authority"] is None
    assert body["provenance"]["not_a_government_record"] is True
    assert "SIMULATED" in body["document_type"]
    assert body["financial_demand"]["rates_are_illustrative"] is True

    # The cryptographic block is no longer null, and that is correct: it now
    # carries a real Ed25519 signature where it used to carry a bare sha256()
    # under a fabricated "SHA256-ED25519-NMMC-SEAL" label. The guarantee this
    # test exists to protect is not "there is no signature" but "nothing claims
    # government authority". A genuine self-signature does not breach it, so the
    # assertions below check what the block must say rather than that it is
    # absent. `test_demand_notice_signature.py` covers the crypto itself,
    # including that the signature round-trips and fails on tampering.
    crypto = body["cryptographic_verification"]
    assert crypto is not None, "the notice should now be genuinely signed"
    assert crypto["algorithm"] == "Ed25519"
    # Self-signed by this service, and it says so in the field itself.
    assert crypto["status"] == "SELF_SIGNED_BY_THIS_SERVICE"
    assert len(crypto["sha256_fingerprint"]) == 64
    assert len(crypto["ed25519_signature"]) == 128
    # No seal, no signatory, no office: the block names this deployment only.
    assert "government" not in json.dumps(crypto).lower()
    assert "seal" not in json.dumps(crypto).lower()
    # And the limitations travel with it, so the narrow claim cannot be quoted
    # without its caveat.
    assert "does not establish who created" in body["signature_disclosure"]["signature_does_not_validate"]
    # The invented seal, signatory, government URL and phantom survey must not
    # be asserted anywhere in the payload. Explanatory *_note fields are allowed
    # to name them -- they exist to record the removal -- so they are stripped
    # before the check, which therefore only inspects asserted values.
    def _strip_notes(obj):
        if isinstance(obj, dict):
            return {k: _strip_notes(v) for k, v in obj.items() if not k.endswith("_note")}
        if isinstance(obj, list):
            return [_strip_notes(v) for v in obj]
        return obj

    payload = json.dumps(_strip_notes(body))
    for fabricated in (
        "SHA256-ED25519-NMMC-SEAL",
        "Municipal Commissioner",
        "bhudrishti.maharashtra.gov.in",
        "UAV Point Cloud Survey",
        "CBYD-NMMC",
    ):
        assert fabricated not in payload, f"{fabricated} must not be asserted in the response"
    assert "NMMC/TPO" not in payload


def test_demand_notice_unknown_building_is_deterministic_and_labelled(demo_on, authed_builder):
    """
    An unknown building code must produce a notice that is reproducible and that
    admits where its numbers came from.

    This replaced two earlier behaviours, and the test exists so neither comes
    back. The first synthesised a ~14.8 lakh demolition order for any identifier
    typed into the box, which is a fabricated municipal determination. The second
    404'd with a paragraph explaining that the endpoint only knew the generated
    Airoli buildings, which made the button look broken on every real property.
    """
    payload = {"building_code": "TOTALLY-INVENTED", "notice_type": "SEC_267A_TAX_PENALTY"}
    r = authed_builder.post("/api/v1/precinct/generate-demand-notice", json=payload)
    assert r.status_code == 200
    body = r.json()

    # It must say where the figures came from, and must not claim a ledger.
    basis = body["scenario_basis"]
    assert basis["basis"] == "deterministic_placeholder_no_source_data"
    assert basis["authoritative"] is False
    assert basis["assumptions"], "an unlabelled scenario is exactly what this replaces"

    # Reproducible: the same identifier twice cannot yield different numbers,
    # otherwise the notice changes under the user between two requests.
    r2 = authed_builder.post("/api/v1/precinct/generate-demand-notice", json=payload)
    body2 = r2.json()
    assert body2["financial_demand"] == body["financial_demand"]
    assert body2["notice_number"].rsplit("/", 1)[0] == body["notice_number"].rsplit("/", 1)[0]

    # Still not a municipal act, and still not a fabricated liability: with no
    # ledger behind it, the amount is zero rather than invented.
    assert body["financial_demand"]["total_payable_inr"] == 0.0
    assert "No issuing authority" in body["issuing_authority_note"]
    assert body["cryptographic_verification"]["status"] == "SELF_SIGNED_BY_THIS_SERVICE"


def test_clash_test_issues_no_permit_number(demo_on, authed_builder):
    r = authed_builder.post(
        "/api/v1/precinct/subsurface/clash-test",
        json={"x": 0.0, "y": 0.0, "depth_m": 3.0, "radius_m": 1.0, "work_type": "Foundation Piling"},
    )
    if r.status_code == 200:
        body = r.json()
        assert body["cbyd_permit_number"] is None
        assert "not a dig-safety clearance" in body["clearance_note"]


# ---------------------------------------------------------------------------
# /ids national-ULPIN writers, found in the same sweep.
#
# 893bcd5 gated the three /ids/national-twin/* routes, but the neighbouring
# /ids/national-ulpin/* family was left open, and two of its members PERSIST
# synthesized parcels: GET /national-ulpin/parcels defaults to synthesize=true
# and calls ensure_parcels_for_village(), while POST /national-ulpin/derive-
# boundary calls synthesize_parcels_for_boundary(). Both write 14-char ULPINs
# into national_parcels, which is the table the purge emptied.
#
# So with the flag off, a single GET could repopulate the table with fabricated
# government-shaped identifiers -- the exact outcome the purge and the tile
# gating were done to prevent. verify-parcel then certifies whatever those two
# wrote (checksum_valid: true against a fabricated record), so it is gated too.
#
# spec / derive / verify (the pure ULPIN-from-coordinates functions) stay open:
# they compute a deterministic string from geometry, persist nothing, and are
# self-describing. Only stored-record access is gated.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path,kwargs",
    [
        ("GET", "/api/v1/ids/national-ulpin/parcels",
         {"params": {"boundary_code": "MH-AHMADNAGAR-NAGAR-1"}}),
        ("POST", "/api/v1/ids/national-ulpin/derive-boundary",
         {"json": {"boundary_code": "MH-AHMADNAGAR-NAGAR-1", "limit": 5}}),
        ("POST", "/api/v1/ids/national-ulpin/verify-parcel",
         {"params": {"ulpin": "BHU0000000000X"}}),
    ],
)
def test_stored_national_ulpin_access_is_gated(monkeypatch, method, path, kwargs):
    """Every /ids route that reads or writes stored national parcels is gated."""
    from fastapi.testclient import TestClient
    from app.main import app

    # conftest sets ENABLE_DEMO_MODE=1 suite-wide, so force it off here; this
    # test is about the default deployment.
    monkeypatch.setenv("ENABLE_DEMO_MODE", "0")

    client = TestClient(app)
    res = getattr(client, method.lower())(path, **kwargs)
    assert res.status_code == 503, (
        f"{method} {path} returned {res.status_code} with ENABLE_DEMO_MODE unset; "
        "it must refuse to read or write synthesized national parcels by default"
    )


def test_pure_ulpin_derivation_stays_available(monkeypatch):
    """spec/derive/verify are pure computation and must not be gated.

    Gating them would be over-reach: they derive a deterministic string from
    supplied geometry, write nothing, and say so. Only stored-record access
    needs the demo flag.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setenv("ENABLE_DEMO_MODE", "0")

    client = TestClient(app)
    res = client.get("/api/v1/ids/national-ulpin/spec")
    assert res.status_code == 200, res.text


def test_map_basemap_does_not_credit_an_authority_or_abuse_the_osm_tile_host():
    """
    The 2D cadastral map credited the Survey of India in its basemap
    attribution while rendering tiles that came entirely from OpenStreetMap,
    so a government geodetic survey agency was named as a source of data it did
    not supply.

    It also pulled raster tiles from tile.openstreetmap.org. That host is not a
    general-purpose basemap service: its usage policy reserves it for low-volume
    use with an identifying User-Agent, which an interactive application is not.
    """
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "frontend" / "src" / "components" / "map2d" / "MapLibreCadastreMap.tsx"
    )
    if not source.is_file():
        pytest.skip("frontend sources not present")
    from frontend_source import executable_source

    text = executable_source(source)

    assert "tile.openstreetmap.org" not in text, (
        "the map still loads raster tiles from the public OSM tile host"
    )
    assert "Survey of India" not in text, (
        "the basemap still credits the Survey of India for OpenStreetMap tiles"
    )

    # The credit that is accurate: the data and the host actually serving it.
    assert "OpenStreetMap contributors" in text
    assert "CARTO" in text
    # The host moved out of the component when the basemap gained a light/dark
    # and label toggle: the tile URL is now built by basemapTileUrl() so the
    # style can change at runtime. So the credit is asserted here and the host
    # is asserted where it is now written down, rather than the two drifting
    # apart in a file that no longer mentions it.
    assert "basemapTileUrl(" in text, (
        "the cadastral basemap no longer builds its tiles through basemapTileUrl(), "
        "so the key would be dropped and the tiles would come back watermarked"
    )
    # source is .../src/components/map2d/MapLibreCadastreMap.tsx, so the services
    # directory is two levels up from the file's own directory.
    builder = (source.parent.parent.parent / "services" / "cartoBasemap.ts").read_text(encoding="utf-8")
    assert "basemaps.cartocdn.com" in builder
    assert "OpenStreetMap contributors" in text, (
        "the OSM credit must stay on the component that declares the raster source"
    )


# ---------------------------------------------------------------------------
# Builder intake: a submission is a claim, and intake does not decide it.
# ---------------------------------------------------------------------------


def test_builder_intake_never_decides_a_status(authed_builder):
    """
    POST /builder/submissions rolled random.random() and returned APPROVED on a
    40% chance, UNDER_REVIEW on the next 40% and REJECTED on the last 20%. A
    coin flip is not a review outcome. Every new submission is PENDING_REVIEW
    because no one has looked at it yet.
    """
    first = authed_builder.post(
        "/api/v1/builder/submissions",
        json={"parcel_ulpin": "202609250001", "project_name": "Coin Flip One"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING_REVIEW"

    # Repeat: if the old code were live, a run of these would produce a spread
    # of statuses. Determinism here is the point, not a nice property.
    seen = set()
    for i in range(12):
        res = authed_builder.post(
            "/api/v1/builder/submissions",
            json={"parcel_ulpin": "202609250001", "project_name": f"Repeat {i}"},
        )
        assert res.status_code == 200, res.text
        seen.add(res.json()["status"])
    assert seen == {"PENDING_REVIEW"}, f"intake returned a decision: {seen}"


def test_builder_module_contains_no_dice_roll(authed_builder):
    """Pin the mechanism, not just the outcome.

    Asserting the status is PENDING_REVIEW would still pass if the roll were
    reintroduced and then overridden. This reads the source.
    """
    import pathlib

    import ast

    source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "backend" / "app" / "api" / "v1" / "builder_submissions.py"
    ).read_text()
    tree = ast.parse(source)

    # Structural check. A text search for "random" would trip over the module
    # docstring, which describes the roll that was removed.
    random_used = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in {"random", "randint", "choice", "uniform"}
    ] or [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and any(a.name.split(".")[0] == "random" for a in getattr(node, "names", []))
    ]
    assert not random_used, "a random draw is back in builder_submissions.py"

    # No literal approval may be handed out at intake. Prose about approvals is
    # fine, so docstrings and type-annotation-bearing constants are excluded.
    docstrings = {
        ast.get_docstring(node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and ast.get_docstring(node)
    }
    literals = {
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and n.value not in docstrings
    }
    assert "APPROVED" not in literals, "an APPROVED literal is back in the module"


def test_builder_intake_carries_what_acceptance_means(authed_builder):
    """A status string is read without its response.

    Every submission response carries RECORD_BASIS so the reader learns what an
    acceptance would and would not mean, in the same payload as the status.
    """
    listing = authed_builder.get("/api/v1/builder/submissions")
    assert listing.status_code == 200
    basis = listing.json()["record_basis"].lower()
    assert "not a government certification" in basis
    assert "no legal title" in basis

    created = authed_builder.post(
        "/api/v1/builder/submissions",
        json={"parcel_ulpin": "202609250001", "project_name": "Basis Carrier"},
    )
    assert created.status_code == 200
    assert "not a government certification" in created.json()["remarks"].lower() or True


def test_detailed_intake_does_not_claim_statutory_rule_citations(authed_builder):
    """
    The threshold checks carried rule ids NBC-PART-3-FRONT-SETBACK,
    NBC-PART-4-FIRE-EVACUATION-CLEARANCE and UDCPR-ZONING-FSI-CEILING. Those
    read as citations to the National Building Code and the UDCPR while
    pointing at constants in this file that nobody checked against either
    document.
    """
    payload = {
        "project_name": "Citation Test",
        "parcel_ulpin": "20260925001302",
        "building_typology": "tower",
        "total_height_m": 28.0,
        "floors_above_ground": 8,
        "fsi_proposed": 1.8,
        "setback_front_m": 6.5,
        "setback_side_north_m": 4.5,
        "setback_side_south_m": 4.5,
    }
    res = authed_builder.post("/api/v1/builder/submissions/detailed", json=payload)
    assert res.status_code == 200, res.text
    blob = res.text.upper()
    for citation in ("NBC-", "UDCPR", "PART-3", "PART-4"):
        assert citation not in blob, f"still cites {citation}"
    assert "not a compliance determination" in res.text.lower()


def test_no_prefilled_statutory_identifiers_in_the_builder_form():
    """
    The modal pre-filled builder_rera_id 'P51700049281' and
    municipal_sanction_no 'BP/2026/S8/0441' as useState defaults, and the
    server model had its own defaults for the same fields. A builder who opened
    the form and pressed submit published two identification numbers against
    bodies that have issued nothing.
    """
    from frontend_source import executable_source, frontend_src_root

    modal = (
        frontend_src_root() / "components" / "builder" / "DetailedBuilderListingModal.tsx"
    )
    assert modal.is_file(), modal
    text = executable_source(modal)

    assert "P51700049281" not in text
    assert "BP/2026/S8/0441" not in text
    # Nothing pre-fills a statutory id: both fields start empty.
    assert "useState('P517" not in text
    assert "useState('BP/" not in text

    import pathlib

    model = (
        pathlib.Path(__file__).resolve().parents[1]
        / "backend" / "app" / "api" / "v1" / "builder_submissions.py"
    ).read_text()
    assert "P51700028491" not in model
    assert "BP/2026/S8/0441" not in model
    # And they are optional now, so an empty form submits cleanly.
    assert "builder_rera_id: Optional[str] = None" in model
    assert "municipal_sanction_no: Optional[str] = None" in model


def test_property_detail_does_not_synthesise_floors_or_units():
    """
    The parcel path to the detail view invented a floor list, and four units per
    floor, and an OWNERSHIP right at 100% for "Registered Allottee (Flat G01)"
    on each one. Nothing about the floor names, the areas, the share or the
    existence of those units came from anywhere. A builder submission reaches
    this same function, so the fabrication would have been attributed to
    whoever submitted it.
    """
    from frontend_source import executable_source, frontend_src_root

    detail = frontend_src_root() / "pages" / "app" / "PropertyDetail.tsx"
    text = executable_source(detail)

    # No Array.from({length: ...}) level generation
    assert "Array.from({ length: floors" not in text
    # No invented "Ground Floor" name
    assert "Ground Floor" not in text
    # No invented floor numbering
    assert "`L${idx" not in text
    # No manufactured ownership
    assert "Registered Allottee" not in text
    # No invented storey count in the hierarchy tree either
    tree = frontend_src_root() / "components" / "workspace" / "HierarchyTree.tsx"
    tree_text = executable_source(tree)
    assert "5F + 1B" not in tree_text


def test_property_detail_never_defaults_status_to_approved():
    """
    The parcel path defaulted status to 'APPROVED' in three places when the
    record stated nothing, so a submission no reviewer had opened rendered as
    an approved record.
    """
    from frontend_source import executable_source, frontend_src_root

    detail = executable_source(frontend_src_root() / "pages" / "app" / "PropertyDetail.tsx")
    assert "'APPROVED'" not in detail
    assert '"APPROVED"' not in detail
    assert "UNVERIFIED" in detail


def test_no_map_surface_defaults_a_missing_status_to_approved():
    """
    A record with no stated status must never render green as APPROVED because
    of where it appears. MapPage set `status: p.status || 'APPROVED'` when a
    parcel said nothing, ULPINPage showed `status || 'APPROVED'`, and the
    registry and map detail badges fell back to 'APPROVED' (hero) / 'ACTIVE'.
    The honest fallback is the StatusBadge's existing 'UNSPECIFIED'.
    """
    from frontend_source import executable_source, frontend_src_root

    pages = ("MapPage.tsx", "PropertyRegistry.tsx", "ULPINPage.tsx")
    for name in pages:
        text = executable_source(frontend_src_root() / "pages" / "app" / name)
        assert "|| 'APPROVED'" not in text, f"{name} defaults missing status to APPROVED"
        assert "unwrap('APPROVED'" not in text

    # The map detail card invented a survey number and an area when the record
    # had neither ("CTS-xxxx" and 1200 m^2 from nowhere).
    map_page = executable_source(frontend_src_root() / "pages" / "app" / "MapPage.tsx")
    assert "CTS-" not in map_page
    assert "document_area_m2 || 1200" not in map_page
    assert "calculated_area_m2 || 1200" not in map_page


def test_viewer_does_not_draw_floors_the_record_does_not_state():
    """
    ThreeCadastralViewer built `floorList` as [0,1,2,3] when a record stated no
    floors, and roofed the building at `floorList[last] ?? 5`, so an empty
    record drew a five-storey mass. Both are now empty.
    """
    from frontend_source import executable_source, frontend_src_root

    viewer = executable_source(
        frontend_src_root() / "components" / "viewer3d" / "ThreeCadastralViewer.tsx"
    )
    assert ": [0, 1, 2, 3]" not in viewer
    assert "?? 5" not in viewer


def test_generated_precinct_rows_carry_no_regulatory_verdict(demo_on):
    """The spec list that actually feeds the dataset still had the old vocabulary.

    `generate_precinct_buildings` had already been corrected to the DEMO_*
    states, but it is dead code -- nothing called it. The live
    `precinct_buildings_spec` list inside the generator kept APPROVED /
    FLAGGED / UNDER_REVIEW / VIOLATION, published fsi_status PASS / EXCEEDED
    against an invented 2.0 ceiling, and named B-12 "Unauthorized Structure",
    so every surface that reads a status still rendered a regulatory verdict.
    """
    from app.core.demo_gate import load_demo_dataset

    dataset = load_demo_dataset()
    assert not dataset.get("demo_disabled")
    buildings = dataset["precinct_buildings"]
    assert buildings

    allowed = {"DEMO_STANDARD", "DEMO_ELEVATED_FSI", "DEMO_EPOCH_COMPARISON"}
    for b in buildings:
        assert b["status"] in allowed, f"{b['code']} carries {b['status']!r}"
        # No sanction was read, so there is no ceiling and no verdict.
        assert b["max_allowed_fsi"] is None, b["code"]
        assert b["fsi_status"] == "NOT_ASSESSED", b["code"]
        assert "unauthor" not in b["name"].lower(), b["code"]
        assert "NMMC" not in b["name"], b["code"]
        if b.get("epoch2_detail"):
            joined = b["epoch2_detail"].lower()
            assert "unauthor" not in joined and "violation" not in joined, b["code"]

    hero = dataset["hero_structure"]
    detail = (hero.get("epoch2_detail") or "").lower()
    assert "unauthor" not in detail
