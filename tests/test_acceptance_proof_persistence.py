"""Three gaps where a response said more than the record behind it kept.

* **GAP 1** -- ``POST /builder/submissions/{id}/disposition`` derived a
  prototype identifier and chained an audit event, returned both, and wrote
  neither onto the stored submission. The ReviewPage panel reads the *listed*
  submission, so the proof existed for one browser session and was gone on
  reload: a proof you cannot come back and read is not an auditable one.

* **GAP 2** -- R013 to R016 (concurrent ownership claims, volumetric overlap
  between distinct registered units, a registered unit with no recorded title,
  an approved unit on disputed or lapsed title) shipped in
  ``app.qa_engine.ownership_clash`` but were reachable only by instantiating
  that detector by hand. ``TopologyQAEngine.run_all_rules`` ran 12 rules and the
  validation route reported 12, so a caller asking the engine whether its units
  carried contradictory title was told they did not.

* **GAP 3** -- the VC-X hero parcel was written with ``[[145, 144], ...]``: metres
  in the extractor's local frame, stored in ``parcels.polygon_geojson`` and
  served from ``GET /parcels/geojson`` as GeoJSON, where they read as 145°E 144°N.

Everything here runs without a database. The persistence layer is stubbed where
the assertion is about what the store was told (GAP 1) and the geometry helpers
are pure functions (GAP 3).
"""
import inspect
import re

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import pipelines_api
from app.api.v1.builder_submissions import _acceptance_record
from app.core import geometry
from app.core.cadastre_store import AIROLI_ORIGIN, shoelace_area_m2
from app.qa_engine.rules import RuleSeverity, RuleStatus, TopologyQAEngine
from tests.conftest import _login

RING_A = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
RING_OVERLAP = [(5.0, 0.0), (15.0, 0.0), (15.0, 10.0), (5.0, 10.0), (5.0, 0.0)]
RING_FAR = [(50.0, 50.0), (60.0, 50.0), (60.0, 60.0), (50.0, 60.0), (50.0, 50.0)]
RING_OTHER = [(20.0, 20.0), (30.0, 20.0), (30.0, 30.0), (20.0, 30.0), (20.0, 20.0)]

# The parcel the units sit inside. Big enough to enclose every ring above, so
# R001 (enclosure) and R002 (unit inside the envelope) pass and a failure in this
# file can only be about the rule under test.
ENVELOPE = [(0.0, 0.0), (70.0, 0.0), (70.0, 70.0), (0.0, 70.0), (0.0, 0.0)]

TITLE_RULE_IDS = {"R013", "R014", "R015", "R016"}

# What app.services.builder_records.apply_review_decision returns when the parcel
# has georeferenced geometry: the shape this test needs, copied so the fixture
# cannot drift with the service's internals without this file noticing.
DERIVED_ACCEPTANCE = {
    "persisted": True,
    "table": "verification_cases",
    "case_number": "VC-SUB-TEST",
    "derived_ulpin": "1234567890123499998",
    "derived_ulpin_status": "PROTOTYPE_DERIVED",
    "derivation": {"method": "PROTOTYPE"},
    "derivation_note": "Derived deterministically from the accepted parcel's geometry.",
    "identifier_authority": "NOT_A_REGISTRY_ALLOCATION",
    "blockchain_proof": {
        "chained": True,
        "previous_hash": "0" * 64,
        "hash": "a" * 64,
        "event_type": "SUBMISSION_ACCEPTED",
        "timestamp": "2026-09-25T10:00:00+00:00",
        "table": "audit_events",
        "ed25519_signature": "sig-placeholder",
        "record_fingerprint": "fp-placeholder",
        "signature_note": "Ed25519 over this prototype's own key.",
    },
}


def _verifier(client) -> dict:
    data = _login(client, "district.admin")
    return {"Authorization": f"Bearer {data['access_token']}"}


def _create(authed, name):
    r = authed.post(
        "/api/v1/builder/submissions",
        json={"parcel_ulpin": "202609250042", "project_name": name},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture()
def derived_acceptance(monkeypatch):
    """Makes acceptance produce an identifier and an audit proof, without a DB.

    Monkeypatching the service function (not the endpoint) keeps the endpoint's
    own bookkeeping -- the part that was broken -- under test: it still has to
    read the payload, write it onto the row, and return the same values.
    """
    from app.services import builder_records

    async def _apply_review_decision(db, **kwargs):
        if kwargs["decision"] != "ACCEPTED_FOR_RECORD":
            return {
                "persisted": False,
                "table": "verification_cases",
                "reason": "refused submissions derive no identifier",
            }
        return dict(DERIVED_ACCEPTANCE)

    monkeypatch.setattr(builder_records, "apply_review_decision", _apply_review_decision)


def _reload(client: TestClient, submission_id: str) -> dict:
    """Re-reads the submission the way a page reload does.

    A new TestClient, so nothing can be served out of a request-scoped cache: the
    only thing carrying the proof is the stored row.
    """
    fresh = TestClient(client.app)
    listing = fresh.get("/api/v1/builder/submissions").json()
    return next(s for s in listing["submissions"] if s["id"] == submission_id)


# --------------------------------------------------------------------------- #
# GAP 1 -- the acceptance proof has to outlive the request that produced it
# --------------------------------------------------------------------------- #

def test_acceptance_proof_survives_a_reload(client, authed_builder, derived_acceptance):
    submitted = _create(authed_builder, "Proof Persistence Probe")
    r = client.post(
        f"/api/v1/builder/submissions/{submitted}/disposition",
        headers=_verifier(client),
        json={"decision": "ACCEPTED_FOR_RECORD", "reason": "declared massing reconciles"},
    )
    assert r.status_code == 200, r.text
    response = r.json()

    row = _reload(client, submitted)

    # Everything the response carried has to be readable from the row afterwards,
    # under the names the page already reads.
    for field in (
        "derived_ulpin", "derived_ulpin_status", "derivation_note",
        "identifier_authority", "audit_proof", "ulpin_note",
    ):
        assert field in row, f"{field!r} was returned but never stored on the submission"
        assert row[field] == response[field], f"{field} differs between response and stored row"

    assert row["derived_ulpin"] == DERIVED_ACCEPTANCE["derived_ulpin"]
    assert row["derived_ulpin_status"] == "PROTOTYPE_DERIVED"
    assert row["identifier_authority"] == "NOT_A_REGISTRY_ALLOCATION"
    assert row["status"] == "ACCEPTED_FOR_RECORD"

    proof = row["audit_proof"]
    assert proof["chained"] is True
    assert proof["hash"] == DERIVED_ACCEPTANCE["blockchain_proof"]["hash"]
    assert proof["previous_hash"] == DERIVED_ACCEPTANCE["blockchain_proof"]["previous_hash"]
    assert proof["ed25519_signature"] == "sig-placeholder"
    assert proof["record_fingerprint"] == "fp-placeholder"
    assert proof["signature_note"]
    assert proof["table"] == "audit_events"


def test_the_identifier_is_still_labelled_as_derived_after_a_reload(client, authed_builder, derived_acceptance):
    """Storing the proof must not store it as an allocation.

    The caveat that makes this identifier readable as a prototype computation
    rather than a registry issuance travels in the same payload, so a row that
    kept the value and dropped the caveat would be worse than the original bug.
    """
    submitted = _create(authed_builder, "Proof Caveat Probe")
    client.post(
        f"/api/v1/builder/submissions/{submitted}/disposition",
        headers=_verifier(client),
        json={"decision": "ACCEPTED_FOR_RECORD", "reason": "declared massing reconciles"},
    )
    row = _reload(client, submitted)

    note = row["ulpin_note"].lower()
    assert "not a registry allocation" in note
    assert "confers no title" in note
    assert row["identifier_authority"] == "NOT_A_REGISTRY_ALLOCATION"


def test_a_rejection_does_not_inherit_the_identifier_an_acceptance_derived(client, authed_builder, derived_acceptance):
    """Accept, then refuse. The second decision supersedes the first.

    The proof fields are overwritten rather than left in place, so a reversed
    decision cannot read back with an identifier and an audit proof it never
    earned -- the same defect the reload test is about, in the other direction.
    """
    submitted = _create(authed_builder, "Reversal Probe")
    client.post(
        f"/api/v1/builder/submissions/{submitted}/disposition",
        headers=_verifier(client),
        json={"decision": "ACCEPTED_FOR_RECORD", "reason": "accepted on the declared massing"},
    )
    r = client.post(
        f"/api/v1/builder/submissions/{submitted}/disposition",
        headers=_verifier(client),
        json={"decision": "REJECTED", "reason": "site clearance receipt turned out to be stale"},
    )
    assert r.json()["record_status"] == "REJECTED"

    row = _reload(client, submitted)
    assert row["status"] == "REJECTED"
    assert not row["derived_ulpin"]
    assert not row["audit_proof"]
    assert not row["identifier_authority"]
    assert len(row["review_history"]) == 2
    # And the decision's own write outcome is reported beside it, not by
    # overwriting the receipt that says whether the submission itself was copied.
    assert row["disposition_persistence"]["persisted"] is False
    assert row["persistence"]["table"] == "submissions"


def test_acceptance_record_is_one_source_for_the_response_and_the_row():
    """The two copies cannot drift, because they are the same dictionary."""
    acceptance = _acceptance_record(DERIVED_ACCEPTANCE, DERIVED_ACCEPTANCE["derived_ulpin"])
    assert set(acceptance) == {
        "derived_ulpin", "derived_ulpin_status", "derivation_note",
        "identifier_authority", "audit_proof", "ulpin_note",
    }
    assert acceptance["audit_proof"] is DERIVED_ACCEPTANCE["blockchain_proof"]

    # A receipt from a run that reached no database is not dressed up: no
    # identifier, and a note that says so rather than staying silent.
    refused = _acceptance_record({"persisted": False, "reason": "database unreachable"}, None)
    assert refused["derived_ulpin"] is None
    assert refused["derived_ulpin_status"] is None
    assert refused["audit_proof"] is None
    assert "no identifier could be derived" in refused["ulpin_note"].lower()

    # A non-dict persistence value (never produced, but the old code guarded it)
    # cannot raise here.
    assert _acceptance_record(None, None)["derived_ulpin"] is None


# --------------------------------------------------------------------------- #
# GAP 2 -- R013-R016 run in the pass the engine and the route already run
# --------------------------------------------------------------------------- #

def _unit(number, ring, rights, min_z=0.0, max_z=3.0, status="APPROVED"):
    return {
        "unit_number": number,
        "proposed_3d_id": f"PROTO-L01-{number}",
        "level_code": "L01",
        "min_z": min_z,
        "max_z": max_z,
        "footprint_geojson": {"type": "Polygon", "coordinates": [ring]},
        "status": status,
        "rights": rights,
    }


def _own(party, share=100.0, encumbrance_status="ACTIVE", right_type="OWNERSHIP", valid_to=None):
    right = {
        "right_type": right_type,
        "party_name": party,
        "share_pct": share,
        "encumbrance_status": encumbrance_status,
    }
    if valid_to is not None:
        right["valid_to"] = valid_to
    return right


def _conflicted_units():
    """One batch carrying all four title defects, and nothing else wrong with it."""
    return [
        # R013: two live owners whose recorded shares cannot both be right.
        _unit("101", RING_A, [_own("Asha Rao", 60.0), _own("Vikram Rao", 60.0)]),
        # R014: with 101 -- a distinct unit, a different party, overlapping plan.
        _unit("102", RING_OVERLAP, [_own("Nikhil Menon")]),
        # R015: recorded, and nothing recorded on it at all.
        _unit("103", RING_FAR, []),
        # R016: approved on a title that is disputed. Disjoint in plan from every
        # other unit, so R014 has no second opinion to give on it.
        _unit("104", RING_OTHER,
              [_own("Meenal Shah", encumbrance_status="DISPUTED")], min_z=4.0, max_z=7.0),
    ]


def _engine_report(units):
    engine = TopologyQAEngine()
    parcel_geojson = {"type": "Polygon", "coordinates": [ENVELOPE]}
    return engine.run_all_rules(
        parcel_data={"ulpin": "12345678901234", "polygon_geojson": parcel_geojson,
                     "document_area_m2": 4900.0, "calculated_area_m2": 4900.0},
        structure_data={"footprint_geojson": parcel_geojson},
        levels_data=[],
        units_data=units,
    )


def test_engine_runs_the_title_rules_in_the_same_pass_as_the_spatial_ones():
    res = _engine_report(_conflicted_units())

    assert res["total_rules"] == 16
    findings = {f["rule_id"]: f for f in res["findings"]}
    assert TITLE_RULE_IDS <= set(findings), "R013-R016 are not in the engine's report"

    assert findings["R013"]["status"] == RuleStatus.FAIL
    assert findings["R013"]["details"][0]["conflict_type"] == "OVER_ALLOCATED_TITLE"
    assert findings["R013"]["details"][0]["unit"] == "L01-101"

    # One overlapping pair, named by both units rather than by position in the
    # list, so a future pair inserted ahead of this one cannot silently move it.
    assert findings["R014"]["status"] == RuleStatus.FAIL
    pair = findings["R014"]["details"][0]
    assert {pair["unit_a"], pair["unit_b"]} == {"L01-101", "L01-102"}
    assert pair["holders_a"] != pair["holders_b"]
    assert "Nikhil Menon" in pair["holders_a"] + pair["holders_b"]

    assert findings["R015"]["status"] == RuleStatus.WARNING
    assert findings["R015"]["details"] == ["L01-103"]
    assert findings["R016"]["status"] == RuleStatus.WARNING
    assert findings["R016"]["details"][0]["unit"] == "L01-104"

    # R004 fails on the same 101/102 pair. That is the spatial rule catching the
    # same two volumes, which is the point of the wiring: one set of unit rows,
    # two families of rule reading them, one report.
    failed = {f["rule_id"] for f in res["findings"] if f["status"] == RuleStatus.FAIL}
    assert failed == {"R004", "R013", "R014"}
    assert res["failed_rules"] == 3
    assert res["overall_status"] == "FAIL"

    # One report, one set of totals -- the ownership block is folded in rather
    # than handed back as a second report the caller has to remember to read.
    assert res["passed_rules"] + res["failed_rules"] + res["warning_rules"] == res["total_rules"]
    ownership = res["ownership_report"]
    assert ownership["total_rules"] == 4
    assert ownership["failed_rules"] == 2
    assert ownership["authoritative"] is False
    assert ownership["evidence_basis"] == "RECORD_COMPARISON"
    assert "not a determination of legal title" in ownership["disclaimer"]


def test_engine_keeps_its_spatial_verdicts_separable_from_the_title_ones():
    """The four extra rules are additive: R001-R012 answer exactly as before."""
    clean = [_unit("201", RING_A, [_own("Asha Rao", 50.0), _own("Vikram Rao", 50.0)])]
    res = _engine_report(clean)
    findings = {f["rule_id"]: f for f in res["findings"]}

    assert res["failed_rules"] == 0
    assert findings["R001"]["status"] == RuleStatus.PASS
    assert findings["R004"]["status"] == RuleStatus.PASS
    # Co-ownership that adds up is not a conflict, and a single party holding
    # both sides of an overlap is a partition question, not a title one.
    assert findings["R013"]["status"] == RuleStatus.PASS
    assert findings["R014"]["status"] == RuleStatus.PASS


def test_an_empty_register_is_not_reported_as_a_clean_run():
    """No unit rows means the title checks never ran, so they cannot pass."""
    res = _engine_report([])
    findings = {f["rule_id"]: f for f in res["findings"]}
    assert res["total_rules"] == 16
    assert res["ownership_report"]["overall_status"] == "NO_RECORDS"
    for rule_id in TITLE_RULE_IDS:
        assert findings[rule_id]["status"] == RuleStatus.WARNING
        assert "did not run" in findings[rule_id]["message"]
    assert res["overall_status"] == "WARNING"


def test_validation_route_reports_the_title_rules(client):
    body = client.get("/api/v1/validation/run")
    assert body.status_code == 200, body.text
    data = body.json()

    assert data["total_rules"] == 16
    rule_ids = {f["rule_id"] for f in data["findings"]}
    assert TITLE_RULE_IDS <= rule_ids, f"/validation/run hides the title rules: {sorted(rule_ids)}"

    ownership = data["ownership_clash"]
    assert ownership["ran"] is True
    assert ownership["rule_ids"] == ["R013", "R014", "R015", "R016"]
    assert ownership["total_rules"] == 4
    assert ownership["evidence_basis"] == "RECORD_COMPARISON"
    assert ownership["authoritative"] is False
    assert ownership["register_populated"] is True
    assert ownership["as_of"]
    assert "not a registry of deeds" in ownership["disclaimer"]


def test_validation_route_cannot_report_a_title_rule_as_a_verdict(client):
    """The four rules are evidence-gathering. A route response must not dress
    them as an authority's determination, so the limitation travels with them."""
    data = client.get("/api/v1/validation/run").json()
    banned = ("fraud", "forged", "invalid title", "unauthorised", "unauthorized", "illegal", "court")
    # A recommended action either says nothing needs doing or hands the matter on:
    # to adjudication, to the authority that holds the instruments, or to whoever
    # has to confirm one. It may not read as a ruling this system has made.
    referrals = ("adjudication", "competent authority", "source register", "re-confirm")

    checked = 0
    for finding in data["findings"]:
        if finding["rule_id"] not in TITLE_RULE_IDS:
            continue
        checked += 1
        lowered = finding["message"].lower()
        for word in banned:
            assert word not in lowered, finding["message"]
        action = finding["recommended_action"]
        assert action is None or any(w in action.lower() for w in referrals), action
    assert checked == 4


def test_rule_catalogue_lists_every_rule_the_engine_runs(client):
    """A catalogue that omits rules the engine runs describes another engine."""
    catalogue = client.get("/api/v1/validation/rules").json()
    catalogue_ids = {entry["rule_id"] for entry in catalogue}

    assert len(catalogue) == 16
    assert catalogue_ids == {f"R{n:03d}" for n in range(1, 17)}

    for entry in catalogue:
        if entry["rule_id"] in TITLE_RULE_IDS:
            assert entry["description"]
            assert entry["evidence_basis"] == "RECORD_COMPARISON"

    engine_ids = {f["rule_id"] for f in client.get("/api/v1/validation/run").json()["findings"]}
    assert engine_ids == catalogue_ids


# --------------------------------------------------------------------------- #
# GAP 3 -- the hero parcel is written in the frame the column promises
# --------------------------------------------------------------------------- #

def test_hero_parcel_boundary_is_real_wgs84_not_the_extractors_metres():
    boundary = pipelines_api._hero_parcel_boundary()
    assert boundary is not None

    ring = geometry.geojson_exterior_ring(boundary["polygon_geojson"])
    assert geometry.classify_frame(ring) == geometry.FRAME_WGS84
    assert geometry.is_georeferenced(ring), "145/144 metres reached a WGS84 column"

    # Inside India's bounds, and nowhere near the old value: the metres used to
    # be served as if they were degrees, which is 145°E 144°N.
    for lon, lat in ring:
        assert geometry.INDIA_LON_RANGE[0] <= lon <= geometry.INDIA_LON_RANGE[1]
        assert geometry.INDIA_LAT_RANGE[0] <= lat <= geometry.INDIA_LAT_RANGE[1]

    # Closed ring, so a GeoJSON consumer gets a polygon rather than a polyline.
    coords = boundary["polygon_geojson"]["coordinates"][0]
    assert coords[0] == coords[-1]

    # The projected half describes the same 30 x 17 m rectangle the extractor
    # measured, and it is the SRID the parcels.geom column is declared in.
    assert re.match(r"SRID=32643;POLYGON\s*\(\(", boundary["polygon_wkt_2d"])
    assert abs(shoelace_area_m2(geometry.anchor_local_ring(pipelines_api.HERO_PARCEL_RING_M)) - 510.0) < 1e-6


def test_the_ewkt_is_wkt_postgis_can_read():
    """`SRID=n;` + a WKT string. The ring needs its own parentheses or PostGIS
    rejects the value at the first coordinate -- which is what happens to the
    `POLYGON(x y, ...)` spelling the shared helper used to emit."""
    from shapely.geometry import Polygon as ShapelyPolygon
    from shapely import from_wkt

    ewkt = pipelines_api._hero_parcel_boundary()["polygon_wkt_2d"]
    srid, _, wkt = ewkt.partition(";")
    assert srid == "SRID=32643"
    assert re.match(r"^POLYGON\s*\(\(.*\)\)$", wkt), wkt

    # Parsed back by a real WKT reader: 30 x 17 m of plan, and the ring closed.
    parsed = ShapelyPolygon(from_wkt(wkt))
    assert abs(parsed.area - 510.0) < 0.01
    assert parsed.exterior.coords[0] == parsed.exterior.coords[-1]


def test_hero_parcel_says_its_position_is_an_assumption():
    """The anchored position is not a survey, and the row has to carry that."""
    basis = pipelines_api._hero_parcel_boundary()["geometry_basis"]
    assert basis["geometry_frame"] == geometry.FRAME_LOCAL_METRES
    assert basis["georeferenced"] is False
    assert basis["anchor_origin"]["easting"] == AIROLI_ORIGIN["easting"]
    assert basis["anchor_origin"]["northing"] == AIROLI_ORIGIN["northing"]
    assert basis["anchor_origin"]["srid"] == 32643
    assert "not a survey" in basis["anchor_note"]
    assert "approximate position" in basis["geometry_note"]


def test_a_degree_ring_is_not_anchored_twice():
    """Idempotence: converting what this function produced changes nothing."""
    once = pipelines_api._hero_parcel_boundary()["polygon_geojson"]
    twice = pipelines_api._hero_parcel_boundary(geometry.geojson_exterior_ring(once))

    assert twice["anchored"] is False
    assert twice["geometry_basis"]["georeferenced"] is True
    assert twice["geometry_basis"]["geometry_frame"] == geometry.FRAME_WGS84
    assert twice["polygon_geojson"]["coordinates"][0] == once["coordinates"][0]


def test_a_ring_of_unclassifiable_numbers_is_refused_not_placed():
    """Two vertices are not a polygon, and nothing is guessed to make them one."""
    assert pipelines_api._hero_parcel_boundary([[0.0, 0.0], [1.0, 1.0]]) is None
    assert pipelines_api._hero_parcel_boundary([[0.0, 0.0], [1.0, 1.0], [2.0, float("nan")]]) is None


def test_the_caller_no_longer_hands_metres_to_the_geojson_column():
    """Source gate, so the fix cannot be undone by re-inlining a literal.

    The write has to hand over what `_hero_parcel_boundary` produced. Bare
    coordinates written straight into `polygon_geojson` are exactly the lie this
    gap is about, so they are refused by name here.
    """
    source = inspect.getsource(pipelines_api._persist_run_result)
    assert 'polygon_geojson=boundary["polygon_geojson"]' in source
    assert '"coordinates": [[' not in source
    assert "polygon_geojson={" not in source
    # And the projected half it stores alongside is the matching EWKT.
    assert 'polygon_wkt_2d=boundary["polygon_wkt_2d"]' in source
