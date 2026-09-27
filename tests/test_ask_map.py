"""Tests for the DB-backed Ask-the-Map endpoint (``POST /api/v1/queries/ask``).

The endpoint used to resolve every question against the generated demo dataset,
so a deployment holding no real records still answered with plausible counts and
a simulated mortgage. It now resolves against what the deployment really holds:
the database (parcels, structures, submissions, admin boundaries, spatial
units, verification cases, rights, recorded changes), the open-data registry
cache, and the generated dataset only while ``ENABLE_DEMO_MODE`` is on.

These tests pin the two behaviours that matter:

* every answer carries the provenance of the rows it matched, including whether
  those rows claim to be authoritative;
* a field no real source covers is reported ``NOT_AVAILABLE`` with the reason,
  never filled in -- there is no title registry, planning authority, approval
  record or zoning plan connected to this deployment, and a compliance verdict
  is exactly the kind of answer a user acts on.

The database and the open-data registry are monkeypatched rather than relied
on: the point is which source an answer is built from, not whether a
particular Postgres happens to be reachable.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest


def _parcel_row(ulpin: str = "MH-01-001-0001", **overrides: Any) -> Dict[str, Any]:
    row = {
        "ulpin": ulpin,
        "survey_number": "123/4A",
        "status": "ACTIVE",
        "document_area_m2": 412.5,
        "calculated_area_m2": 409.1,
        "gis_area_m2": None,
        "data_provenance": "openstreetmap",
        "provenance_authoritative": False,
        "address": "Airoli, Navi Mumbai",
        "locality": "Airoli",
    }
    row.update(overrides)
    return row


def _structure_row(building_code: str = "B-17", **overrides: Any) -> Dict[str, Any]:
    row = {
        "building_code": building_code,
        "name": "Demo Tower",
        "structure_type": "RESIDENTIAL",
        "height_m": 24.0,
        "floors_count": 8,
        "basements_count": 1,
        "total_built_up_area_m2": 3200.0,
        "calculated_fsi": 0.8,
        "height_basis": "inferred_from_tags",
        "observed_height_m": None,
        "extraction_source": "globalml",
        "data_provenance": "globalml",
        "provenance_authoritative": False,
        "is_verified": False,
        "parcel_ulpin": "MH-01-001-0001",
        "footprint_geojson": {
            "type": "Polygon",
            "coordinates": [[[72.99, 19.09], [72.991, 19.09], [72.991, 19.091], [72.99, 19.091], [72.99, 19.09]]],
        },
        "ground_elevation_z": 2.0,
    }
    row.update(overrides)
    return row


def _db_index(parcels: Optional[List[Dict[str, Any]]] = None, **tables: List[Dict[str, Any]]):
    """Build a fake ``_db_index`` result: rows per table, no errors."""
    from app.api.v1 import ask_map

    rows = {name: [] for name in ask_map._DB_READS}
    rows["parcels"] = list(parcels or [])
    for name, table_rows in tables.items():
        rows[name] = list(table_rows)
    return lambda: (rows, {})


def _opendata_index(regions: Optional[List[Dict[str, Any]]] = None, footprints: int = 0):
    def _fake() -> Dict[str, Any]:
        return {
            "regions": list(regions or []),
            "providers_configured": ["openstreetmap"],
            "providers_unconfigured": ["data.gov.in"],
            "footprints": footprints,
        }

    return _fake


# --------------------------------------------------------------------------- #
# Provenance on every result                                                   #
# --------------------------------------------------------------------------- #


def test_every_answer_carries_a_provenance_block():
    """No answer is assembled without provenance; the block is always present."""
    from app.api.v1 import ask_map

    dataset = ask_map.load_demo_dataset()
    if dataset.get("demo_disabled"):
        pytest.skip("demo dataset disabled")

    for phrase in (
        "show underground clashes",
        "show me a mortgage on flat 201",
        "any unauthorized change to the building",
        "how many are pending review",
        "how many buildings",
        "find the property at Airoli",
    ):
        parsed = ask_map.parse_query_deterministically(phrase, dataset)
        prov = parsed["provenance"]
        assert isinstance(prov.get("sources"), list), phrase
        assert "record_count" in prov and "authoritative" in prov, phrase
        assert "synthetic_included" in prov, phrase
        # The top-level synthetic flag is derived from the same block, so the
        # two cannot disagree about whether generated data took part.
        assert parsed["synthetic"] is prov["synthetic_included"], phrase


def test_pinned_dataset_is_labelled_synthetic_and_never_authoritative():
    """Generated records are reported as generated, whatever they contain."""
    from app.api.v1 import ask_map

    dataset = ask_map.load_demo_dataset()
    if dataset.get("demo_disabled"):
        pytest.skip("demo dataset disabled")

    parsed = ask_map.parse_query_deterministically("show underground clashes", dataset)
    assert parsed["synthetic"] is True
    assert parsed["provenance"]["synthetic_included"] is True
    assert parsed["provenance"]["authoritative"] is False
    kinds = {s["kind"] for s in parsed["provenance"]["sources"]}
    assert kinds == {"demo-dataset"}


def test_pinned_dataset_does_not_touch_the_database(monkeypatch: pytest.MonkeyPatch):
    """A pinned record set is the whole world for that answer.

    This is also the real-data-only configuration: an empty pinned set must
    answer "nothing matched" rather than quietly reaching for the database.
    """
    from app.api.v1 import ask_map

    def _boom(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("a pinned dataset must not consult the database")

    monkeypatch.setattr(ask_map, "_db_index", _boom)
    monkeypatch.setattr(ask_map, "_opendata_index", _boom)

    parsed = ask_map.parse_query_deterministically("show me a mortgage on flat 201", {})
    assert parsed["category"] == "RIGHTS_SEARCH"
    assert parsed["matched_ids"] == []
    assert parsed["filter"]["matched"] is False


def test_pinned_empty_set_reports_nothing_matched_for_every_record_category(
    monkeypatch: pytest.MonkeyPatch,
):
    """A pinned set that holds nothing answers about *those records*, not the deployment.

    Each category has its own worded "nothing here" message -- no subsurface
    object is clashing, no mortgage is recorded, no change is on file. Those are
    claims about what a deployment holds, and a caller who pinned a record set
    has excluded the deployment from the question. Reporting them anyway would
    let a scenario assert an absence in the deployment it never consulted, which
    is the mirror image of the bug this endpoint had: answering from a source
    that was not part of the question.
    """
    from app.api.v1 import ask_map

    def _boom(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("a pinned dataset must not consult the database")

    monkeypatch.setattr(ask_map, "_db_index", _boom)
    monkeypatch.setattr(ask_map, "_opendata_index", _boom)
    monkeypatch.setattr(ask_map, "_CASES_DB", [])

    empty = {"demo_disabled": False}
    for phrase, category in (
        ("is there an underground clash", "UNDERGROUND_CLASH_SEARCH"),
        ("show me a mortgage on flat 201", "RIGHTS_SEARCH"),
        ("any unauthorized change to the building", "CHANGE_SEARCH"),
        ("how many are pending review", "VERIFICATION_STATUS"),
    ):
        parsed = ask_map.parse_query_deterministically(phrase, empty)
        assert parsed["category"] == category, phrase
        assert "No record in the demo dataset matches" in parsed["explanation"], phrase
        assert parsed["matched_ids"] == [], phrase
        assert parsed["filter"]["matched"] is False, phrase
        assert parsed["highlight"]["focus_point"] is None, phrase


def test_generated_demo_cases_do_not_answer_with_the_gate_shut(
    monkeypatch: pytest.MonkeyPatch,
):
    """The demo verification ledger is gated here, not by its own module.

    ``verification._CASES_DB`` is two hardcoded invented cases that the demo gate
    does not reach, so the gate is applied at the point of use: with it shut the
    answer is about the ``verification_cases`` table, which is empty here, and
    not about a queue that only exists while the showcase is switched on.
    """
    from app.api.v1 import ask_map

    assert ask_map._CASES_DB, "the demo ledger is expected to hold invented cases"

    monkeypatch.setenv("ENABLE_DEMO_MODE", "")
    monkeypatch.setattr(ask_map, "_db_index", _db_index())
    monkeypatch.setattr(ask_map, "_opendata_index", _opendata_index())

    parsed = ask_map.parse_query_deterministically("how many are pending review")
    assert parsed["category"] == "VERIFICATION_STATUS"
    assert parsed["matched_ids"] == []
    assert parsed["filter"]["matched"] is False
    assert parsed["synthetic"] is False
    assert parsed["provenance"]["sources"] == []
    # Unpinned, so the deployment itself was searched and its absence is worth
    # stating: this is a claim about the records the deployment holds, which is
    # exactly what an unpinned question asked.
    assert "nothing is pending anywhere" in parsed["explanation"]


def test_generated_demo_records_are_excluded_from_coverage_and_counts(
    monkeypatch: pytest.MonkeyPatch,
):
    """Coverage and counts drop generated records, denominator included.

    Both answers add a demo total to a real total. Leaving the generated records
    in the arithmetic while dropping them from the reported sources would give a
    figure that counts rows the answer then refuses to name.
    """
    from app.api.v1 import ask_map

    dataset = ask_map.load_demo_dataset()
    if dataset.get("demo_disabled"):
        pytest.skip("demo dataset disabled")
    assert dataset.get("precinct_buildings"), "the demo dataset is expected to hold buildings"

    monkeypatch.setenv("ENABLE_DEMO_MODE", "")
    monkeypatch.setattr(ask_map, "_db_index", _db_index())
    monkeypatch.setattr(ask_map, "_opendata_index", _opendata_index())

    counted = ask_map.parse_query_deterministically("how many buildings")
    assert counted["category"] == "COUNT_QUERY"
    assert counted["provenance"]["sources"] == []
    assert counted["filter"]["matched"] is False
    # The invented precinct is not in the total, so nothing is left to count.
    assert "No record in" in counted["explanation"]

    # With the gate shut but a pinned set supplied, the pinned set is still the
    # whole world -- pinning is an explicit instruction, not a gate override.
    pinned = ask_map.parse_query_deterministically("how many buildings", dataset)
    assert pinned["filter"]["dataset_field"] == "precinct_buildings"
    assert f"{len(dataset['precinct_buildings'])}" in pinned["explanation"]


def test_parcel_answer_provenance_comes_from_the_parcels_table(monkeypatch: pytest.MonkeyPatch):
    """A parcel question is answered from stored rows and says so."""
    from app.api.v1 import ask_map

    monkeypatch.setattr(ask_map, "_db_index", _db_index(parcels=[_parcel_row()]))
    monkeypatch.setattr(ask_map, "_opendata_index", _opendata_index())

    parsed = ask_map.parse_query_deterministically("show me the parcels")
    assert parsed["category"] == "PARCEL_RECORD_SEARCH"
    assert "MH-01-001-0001" in parsed["matched_ids"]
    assert "MH-01-001-0001" in parsed["explanation"]

    sources = parsed["provenance"]["sources"]
    assert len(sources) == 1
    src = sources[0]
    assert src["source"] == "postgis:parcels"
    assert src["kind"] == "database"
    assert src["record_count"] == 1
    # The row's own claim is passed through, and one non-authoritative row
    # keeps the whole answer non-authoritative.
    assert src["authoritative"] is False
    assert "openstreetmap" in src["note"]
    assert parsed["provenance"]["authoritative"] is False


def test_structure_answer_includes_the_open_data_registry_source(monkeypatch: pytest.MonkeyPatch):
    """Stored rows and cached footprints are attributed separately."""
    from app.api.v1 import ask_map

    monkeypatch.setattr(ask_map, "_db_index", _db_index(structures=[_structure_row()]))
    monkeypatch.setattr(
        ask_map,
        "_opendata_index",
        _opendata_index(
            regions=[
                {
                    "region": "19.0987_72.9977_r400",
                    "source": "openstreetmap",
                    "counts": {"buildings": 42, "labels": 3},
                }
            ],
            footprints=42,
        ),
    )

    parsed = ask_map.parse_query_deterministically("show me the building source of the structures")
    assert parsed["category"] == "STRUCTURE_SOURCE_SEARCH"
    sources = parsed["provenance"]["sources"]
    kinds = {s["kind"] for s in sources}
    assert kinds == {"database", "open-data-registry"}
    registry = next(s for s in sources if s["kind"] == "open-data-registry")
    assert registry["record_count"] == 42
    # A cached footprint is never a cadastral authority.
    assert registry["authoritative"] is False
    assert "42" in parsed["explanation"]

    # A question about a building's source is answered by the columns that say
    # where it came from, as data and not only as prose: `extraction_source` is
    # where the footprint was lifted from (GlobalML, OpenStreetMap, a pipeline),
    # and `height_basis` is a separate claim about the height. Answering with
    # the height basis alone would answer a question nobody asked.
    assert parsed["filter"]["extraction_sources"] == ["globalml"]
    assert parsed["filter"]["height_bases"] == ["inferred_from_tags"]
    assert "globalml" in parsed["explanation"]
    assert "inferred_from_tags" in parsed["explanation"]

    db = next(s for s in sources if s["kind"] == "database")
    assert db["source"] == "postgis:structures"
    assert db["record_count"] == 1


def test_structure_source_of_a_row_with_no_extraction_record_is_reported_unset(
    monkeypatch: pytest.MonkeyPatch,
):
    """An unset provenance column reads "unset", never a guessed provider.

    Defaulting it would make a structure whose footprint this codebase drew
    indistinguishable from one lifted from a published dataset, which is the one
    distinction the column exists to keep.
    """
    from app.api.v1 import ask_map

    row = _structure_row(extraction_source=None, height_basis=None)
    monkeypatch.setattr(ask_map, "_db_index", _db_index(structures=[row]))
    monkeypatch.setattr(ask_map, "_opendata_index", _opendata_index())

    parsed = ask_map.parse_query_deterministically("what is the footprint source of the structure")
    assert parsed["category"] == "STRUCTURE_SOURCE_SEARCH"
    assert parsed["filter"]["extraction_sources"] == []
    assert parsed["filter"]["height_bases"] == []
    assert "unset" in parsed["explanation"]
    # Nothing was substituted for the missing values.
    for provider in ("globalml", "openstreetmap", "modelled"):
        assert provider not in parsed["explanation"].lower()


def test_table_that_cannot_be_read_is_reported_not_swallowed(monkeypatch: pytest.MonkeyPatch):
    """A missing table costs its own answers and nothing else."""
    from app.api.v1 import ask_map

    def _fake_index():
        rows = {name: [] for name in ask_map._DB_READS}
        errors = {"parcels": "OperationalError: relation \"parcels\" does not exist"}
        return rows, errors

    monkeypatch.setattr(ask_map, "_db_index", _fake_index)
    monkeypatch.setattr(ask_map, "_opendata_index", _opendata_index())

    parsed = ask_map.parse_query_deterministically("show me the parcels")
    assert parsed["category"] == "PARCEL_RECORD_SEARCH"
    assert parsed["matched_ids"] == []
    reported = {item["field"]: item for item in parsed["not_available"]}
    assert "parcels" in reported
    assert reported["parcels"]["status"] == "NOT_AVAILABLE"
    assert "does not exist" in reported["parcels"]["reason"]


# --------------------------------------------------------------------------- #
# Refusing to invent unavailable fields                                        #
# --------------------------------------------------------------------------- #


def test_ownership_question_is_refused_with_reasons():
    """No title registry is connected, so ownership is reported missing.

    The refusal names the missing fields rather than returning an empty answer:
    an empty answer reads as "this property has no title", which is a finding
    about the property rather than a gap in the sources.
    """
    from app.api.v1 import ask_map

    dataset = ask_map.load_demo_dataset()
    parsed = ask_map.parse_query_deterministically("who owns this property", dataset)
    assert parsed["category"] == "REGISTRY_QUERY"
    assert parsed["matched_ids"] == []
    assert parsed["filter"]["matched"] is False

    reported = {item["field"]: item for item in parsed["not_available"]}
    assert set(reported) == {"title", "ownership"}
    for field in ("title", "ownership"):
        assert reported[field]["status"] == "NOT_AVAILABLE"
        assert reported[field]["reason"]

    # Nothing was invented: no owner name, no value, no estimate.
    assert "Not available" in parsed["explanation"]
    assert parsed["provenance"]["record_count"] == 0


def test_approval_and_zoning_questions_are_refused_with_reasons():
    """No approval record and no zoning plan exist to read."""
    from app.api.v1 import ask_map

    dataset = ask_map.load_demo_dataset()
    for phrase in ("is this building approved", "what is the zoning of this building"):
        parsed = ask_map.parse_query_deterministically(phrase, dataset)
        assert parsed["category"] == "COMPLIANCE_QUERY", phrase
        reported = {item["field"]: item for item in parsed["not_available"]}
        assert set(reported) == {"approval_status", "zoning", "permitted_fsi"}, phrase
        for field in reported.values():
            assert field["status"] == "NOT_AVAILABLE"
            assert field["reason"]
        # No compliance verdict is ever fabricated.
        assert "Not available" in parsed["explanation"]


def test_fsi_question_does_not_invent_a_number():
    """A permitted-FSI figure is not computable without a loaded rule."""
    from app.api.v1 import ask_map

    dataset = ask_map.load_demo_dataset()
    parsed = ask_map.parse_query_deterministically("what is the permitted fsi here", dataset)
    assert parsed["category"] == "COMPLIANCE_QUERY"
    reported = {item["field"]: item for item in parsed["not_available"]}
    assert "permitted_fsi" in reported
    # The demo dataset does contain an FSI figure for its invented buildings;
    # it must not be surfaced as an answer to this question.
    assert "permitted_fsi" not in parsed["explanation"]


# --------------------------------------------------------------------------- #
# Demo-mode gating                                                             #
# --------------------------------------------------------------------------- #


def test_generated_data_is_excluded_when_the_demo_gate_is_shut(monkeypatch: pytest.MonkeyPatch):
    """With ENABLE_DEMO_MODE off, no answer is built from generated records."""
    from app.api.v1 import ask_map

    monkeypatch.delenv("OPENDATA_PREWARM_AREAS", raising=False)
    monkeypatch.setenv("ENABLE_DEMO_MODE", "")
    monkeypatch.setattr(ask_map, "_db_index", _db_index())
    monkeypatch.setattr(ask_map, "_opendata_index", _opendata_index())

    parsed = ask_map.parse_query_deterministically("how many buildings")
    assert parsed["category"] == "COUNT_QUERY"
    assert parsed["synthetic"] is False
    assert parsed["provenance"]["synthetic_included"] is False
    assert parsed["provenance"]["sources"] == []
    assert parsed["matched_ids"] == []


# --------------------------------------------------------------------------- #
# HTTP endpoint                                                                #
# --------------------------------------------------------------------------- #


def test_ask_endpoint_returns_provenance_and_not_available(client):
    """The API response carries the same provenance and refusals."""
    res = client.post("/api/v1/queries/ask", json={"query": "who owns this property"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["intent_category"] == "REGISTRY_QUERY"
    assert body["match_count"] == 0
    assert body["synthetic"] is False
    assert body["provenance"]["sources"] == []
    fields = {item["field"] for item in body["not_available"]}
    assert {"title", "ownership"} <= fields
    # The stored-record disclaimer, not the synthetic one: no generated record
    # took part in this answer.
    assert "STORED RECORDS" in body["disclaimer"]


def test_ask_endpoint_reports_stored_rows_with_provenance(client, monkeypatch: pytest.MonkeyPatch):
    """A stored submission is reported as a stored row, with its table named."""
    from app.api.v1 import ask_map

    monkeypatch.setattr(
        ask_map,
        "_db_index",
        _db_index(
            submissions=[
                {
                    "receipt_number": "RCPT-2026-0001",
                    "contributor_type": "BUILDER",
                    "status": "SUBMITTED",
                    "parcel_ulpin": "MH-01-001-0001",
                }
            ]
        ),
    )
    monkeypatch.setattr(ask_map, "_opendata_index", _opendata_index())

    res = client.post("/api/v1/queries/ask", json={"query": "show me the submissions"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["intent_category"] == "SUBMISSION_STATUS"
    assert "RCPT-2026-0001" in body["matched_entity_ids"]
    assert "RCPT-2026-0001" in body["human_explanation"]
    sources = body["provenance"]["sources"]
    assert any(s["source"] == "postgis:submissions" for s in sources)
    # A workflow status is not an approval, and the answer says so.
    assert any("not an approval" in note.lower() for note in body["limitations"])
