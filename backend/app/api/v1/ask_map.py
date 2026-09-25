"""Ask-the-Map: deterministic intent routing over records that actually exist.

An answer is only as good as the row behind it. This endpoint resolved every
question against the generated demo dataset, so a deployment holding no real
records at all still answered with plausible counts, a simulated mortgage and a
synthetic extra floor -- all of it invented at the moment of the question, and
all of it reported as if the dataset were the world.

It now resolves against what the deployment really holds, in three layers, each
row carrying its own recorded provenance:

* the database -- parcels, structures, submissions, admin boundaries, spatial
  units, verification cases, rights and recorded changes, read one table at a
  time so a missing table costs its own answers and nothing else;
* the open-data registry cache (``app.opendata.service``) -- footprints a real
  provider actually returned (OpenStreetMap, Microsoft GlobalML, Bhuvan,
  data.gov.in), read from the cache and never by triggering a fetch, so a
  question arriving over HTTP cannot turn into a provider round-trip;
* the generated demo dataset, only while ``ENABLE_DEMO_MODE`` is on. The gate
  is applied where the generated records are read, not only where the dataset is
  loaded: ``verification._CASES_DB`` is a hardcoded ledger of invented cases that
  the gate does not reach on its own, and a generated record that reached an
  answer with the gate shut would be exactly the failure this file exists to
  remove.

Passing a ``dataset`` pins the record set: the answer is built from exactly
those records and neither the database nor the registry is consulted. That makes
a scenario reproducible, and it also means a pinned set that holds nothing
answers "nothing matched in the records you pinned" rather than describing a
deployment the question excluded.

Every result carries the provenance of the rows it matched, including whether
those rows claim to be authoritative, and anything no real source covers is
reported ``NOT_AVAILABLE`` with the reason instead of being filled in. There is
no title registry, no planning authority, no approval record and no published
cadastral boundary connected to this deployment, so a question about ownership,
title, approval or zoning gets a refusal naming what is missing. Those are the
answers a user acts on, which is exactly why they are not guessed at.

Two earlier defects are pinned by tests here. The previous implementation
returned hardcoded literals -- a fixed pipe code, a fixed rupee mortgage amount,
a fixed 6th-floor finding -- and added a flat 15 ms to the reported duration so
the answer looked like it had done work; it now scans the records and reports
real elapsed time. And the dataset used to be a module-level snapshot taken at
import, so a process started while the demo gate was shut answered every
question from the empty stand-in for its whole life while every other endpoint
re-read per request; everything below is resolved per call.
"""
import json
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.api.v1.verification import _CASES_DB
from app.core.demo_gate import demo_mode_enabled, load_demo_dataset
# Single source of truth for unit rights. Imported rather than reimplemented so
# this endpoint cannot drift from what the 3D scene and /rights report.
from app.scene.scene_architect import _rights_for, center_of

router = APIRouter(prefix="/queries", tags=["Ask-The-Map Natural Language Query Engine"])


_NOT_AVAILABLE = "NOT_AVAILABLE"

# Why an attribute cannot be answered, stated once so every route that touches it
# reports the same thing. Each of these is a real absence, not an outage: no
# registry, authority or publication of that kind is connected to this
# deployment, so no amount of retrying produces an answer.
_UNSOURCED: Dict[str, str] = {
    "parcel_boundary": (
        "No authentic cadastral boundary source is connected. Parcel polygons are "
        "modelled from footprints unless a real ingest wrote them, and each row "
        "says which in data_provenance."
    ),
    "title": (
        "No title or ownership registry is connected. Nothing in this deployment "
        "has been checked against a record of rights."
    ),
    "approval_status": (
        "No planning-authority approval record is connected. No permission, "
        "sanction or rejection from any authority has been obtained or read."
    ),
    "zoning": (
        "No zoning or land-use plan is published to this deployment, so no zone, "
        "FAR band or permitted density can be named."
    ),
    "permitted_fsi": (
        "No permitted-FAR rule is loaded for the jurisdiction, so FSI cannot be "
        "computed or compared against anything."
    ),
    "change_authorisation": (
        "Nothing here establishes whether a change was permitted. A detected "
        "difference is a difference, not a determination."
    ),
    "market_value": (
        "No valuation source is connected; no circle rate, guidance value or "
        "market record has been consulted."
    ),
}


def _not_available(field: str) -> Dict[str, Any]:
    """One attribute no real source covers, with the reason it is missing."""
    return {
        "field": field,
        "status": _NOT_AVAILABLE,
        "reason": _UNSOURCED.get(field, "No real source for this attribute is connected."),
    }


def _unsourced_note(*fields: str) -> str:
    return " ".join(_UNSOURCED[field] for field in fields if field in _UNSOURCED)


_SYNTHETIC_DISCLAIMER = (
    "SYNTHETIC DEMO DATA — every match below is a record in the invented "
    "demo dataset. It is not a legal, title, encumbrance, or statutory record "
    "and does not evidence a real-world finding."
)
_STORED_RECORD_DISCLAIMER = (
    "STORED RECORDS — every match below is a row this deployment actually "
    "stores, reported with the provenance that row carries. A stored geometry or "
    "a recorded workflow status is not a certificate, a title record, or a "
    "determination by any authority."
)
# Kept under the old name: the disclaimer a caller reads depends on what the
# answer was built from, and the synthetic one is still the right text when any
# generated record took part.
_DISCLAIMER = _SYNTHETIC_DISCLAIMER


class AskMapQuery(BaseModel):
    query: str


class AskMapResult(BaseModel):
    query: str
    intent_category: str
    matched_filter: Dict[str, Any]
    matched_entity_ids: List[str]
    highlight_3d: Dict[str, Any]
    human_explanation: str
    execution_time_ms: float
    match_count: int
    data_source: str
    synthetic: bool
    limitations: List[str]
    disclaimer: str
    provenance: Dict[str, Any] = {}
    not_available: List[Dict[str, Any]] = []


# --------------------------------------------------------------------------- #
# Resolution: what this deployment can answer from                             #
# --------------------------------------------------------------------------- #

# One statement per table. Each is read on its own so a table that does not exist
# (unmigrated deployment, or a schema this build predates) is reported as such
# instead of taking the whole endpoint down with it.
_DB_READS: Dict[str, str] = {
    "parcels": """
        SELECT ulpin, survey_number, status, document_area_m2, calculated_area_m2,
               gis_area_m2, data_provenance, provenance_authoritative,
               address, locality
          FROM parcels
         ORDER BY created_at DESC
         LIMIT :limit
    """,
    "structures": """
        SELECT s.building_code, s.name, s.structure_type, s.height_m, s.floors_count,
               s.basements_count, s.total_built_up_area_m2, s.calculated_fsi,
               s.height_basis, s.observed_height_m, s.extraction_source,
               s.data_provenance, s.provenance_authoritative, s.is_verified,
               p.ulpin AS parcel_ulpin
          FROM structures s
          LEFT JOIN parcels p ON p.id = s.parcel_id
         ORDER BY s.created_at DESC
         LIMIT :limit
    """,
    "submissions": """
        SELECT sub.receipt_number, sub.contributor_type, sub.status,
               sub.created_at, p.ulpin AS parcel_ulpin
          FROM submissions sub
          JOIN parcels p ON p.id = sub.parcel_id
         ORDER BY sub.created_at DESC
         LIMIT :limit
    """,
    "admin_boundaries": """
        SELECT code, name, level, parent_code, state_code, district_code,
               taluka_code, village_code, source, centroid_lat, centroid_lng,
               area_km2, population_estimate
          FROM admin_boundaries
         WHERE 1 = 1
         ORDER BY CASE level WHEN 'STATE' THEN 1 WHEN 'DISTRICT' THEN 2
                             WHEN 'TALUKA' THEN 3 ELSE 4 END, name
         LIMIT :limit
    """,
    "spatial_units": """
        SELECT su.code, su.type_code, su.description, su.has_clash, su.clash_details,
               p.ulpin AS parcel_ulpin
          FROM spatial_units su
          JOIN parcels p ON p.id = su.parcel_id
         WHERE su.has_clash
         ORDER BY su.created_at DESC
         LIMIT :limit
    """,
    "verification_cases": """
        SELECT vc.case_number, vc.case_type, vc.status, vc.priority, vc.basis,
               p.ulpin AS parcel_ulpin
          FROM verification_cases vc
          JOIN parcels p ON p.id = vc.parcel_id
         ORDER BY vc.created_at DESC
         LIMIT :limit
    """,
    "rights": """
        SELECT u.unit_number, u.proposed_3d_id, r.right_type, r.encumbrance_status,
               r.mortgage_amount_inr, r.financial_institution, r.is_synthetic,
               py.name AS party_name, py.party_type
          FROM rights r
          JOIN units u ON u.id = r.unit_id
          LEFT JOIN parties py ON py.id = r.party_id
         WHERE r.encumbrance_status = 'ACTIVE'
         ORDER BY r.valid_from DESC
         LIMIT :limit
    """,
    "property_changes": """
        SELECT change_type, epoch_from, epoch_to, status, delta_height_m,
               delta_floors, delta_volume_m3, details
          FROM property_changes
         ORDER BY created_at DESC
         LIMIT :limit
    """,
}

# TALUKA and VILLAGE rows in admin_boundaries are grid-synthesised subdivisions
# clipped to a real parent. While the demo gate is shut they are not searched at
# all, for the reason search.py gives: an honest label on a generated subdivision
# is still a generated subdivision.
_NO_SYNTHETIC_BOUNDARIES = " AND COALESCE(source, 'unknown') <> 'synthetic'"

_DB_SOURCE_DETAIL: Dict[str, str] = {
    "parcels": "parcels table (PostgreSQL/PostGIS)",
    "structures": "structures table, joined to parcels",
    "submissions": "submissions table, joined to parcels",
    "admin_boundaries": "admin_boundaries table",
    "spatial_units": "spatial_units table, joined to parcels",
    "verification_cases": "verification_cases table, joined to parcels",
    "rights": "rights table, joined to units and parties",
    "property_changes": "property_changes table",
}

# How many rows one answer may name. Enough to describe a deployment, small
# enough that the endpoint is not a table dump.
_ROW_LIMIT = 200


def _db_index(limit: int = _ROW_LIMIT) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, str]]:
    """Real rows this deployment holds, read one table at a time.

    A table that cannot be read costs its own answers and nothing else, and the
    reason is kept rather than swallowed: "the parcels table could not be read"
    and "there are no parcels" are different facts and only the first is fixable.
    The result is reported as ``not_available`` for that table.
    """
    from app.core.database import SyncSessionLocal

    rows: Dict[str, List[Dict[str, Any]]] = {}
    errors: Dict[str, str] = {}
    gate_open = demo_mode_enabled()
    try:
        session_factory = SyncSessionLocal
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        reason = f"database session unavailable: {type(exc).__name__}: {exc}"[:200]
        return {}, {name: reason for name in _DB_READS}
    try:
        with session_factory() as db:
            for name, statement in _DB_READS.items():
                sql = statement
                if name == "admin_boundaries" and not gate_open:
                    sql = sql.replace("WHERE 1 = 1", "WHERE 1 = 1" + _NO_SYNTHETIC_BOUNDARIES)
                try:
                    result = db.execute(text(sql), {"limit": max(1, int(limit))})
                    rows[name] = [dict(r) for r in result.mappings().all()]
                except Exception as exc:  # noqa: BLE001 - one table must not sink the rest
                    db.rollback()
                    errors[name] = f"{type(exc).__name__}: {exc}".strip()[:200]
    except Exception as exc:  # noqa: BLE001 - no connection: every table is affected
        errors = {name: f"database unavailable: {type(exc).__name__}: {exc}"[:200] for name in _DB_READS}
    return rows, errors


def _opendata_index(limit: int = 25) -> Dict[str, Any]:
    """Footprints the open-data registry already holds, plus provider status.

    Read from the registry cache only. A question arriving over HTTP must not
    become a provider round-trip, and ``api.data.gov.in`` is unreachable from
    some deployments, so such a call would either stall the request or fail
    inside it. An area nobody has fetched is therefore absent from the answer,
    and the answer says so -- which is the truth, not a gap to be papered over
    by fetching on the spot.
    """
    index: Dict[str, Any] = {
        "regions": [],
        "providers_configured": [],
        "providers_unconfigured": [],
        "footprints": 0,
    }
    try:
        from app.opendata import service
        from app.sources import get_providers, unconfigured_providers

        regions = service.cached_regions(limit=limit)
        index["regions"] = regions
        index["footprints"] = sum(int((r.get("counts") or {}).get("buildings") or 0) for r in regions)
        index["providers_configured"] = [p.name for p in get_providers()]
        index["providers_unconfigured"] = unconfigured_providers()
    except Exception as exc:  # noqa: BLE001 - registry telemetry is not the answer
        index["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return index


def _resolve(dataset: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Everything this question may be answered from, resolved per call.

    A caller that passes ``dataset`` has pinned the record set: the answer is
    built from exactly those records and nothing else is consulted. That is what
    makes a scenario reproducible, and it is also the real-data-only
    configuration -- an empty pinned set must answer "nothing matched" rather
    than quietly reaching for the database and the registry.
    """
    if dataset is not None:
        return {
            "pinned": True,
            "dataset": dataset,
            "db": {},
            "db_errors": {},
            "opendata": {"regions": [], "providers_configured": [], "providers_unconfigured": [], "footprints": 0},
            "demo_included": True,
        }
    db_rows, db_errors = _db_index()
    return {
        "pinned": False,
        "dataset": load_demo_dataset(),
        "db": db_rows,
        "db_errors": db_errors,
        "opendata": _opendata_index(),
        "demo_included": demo_mode_enabled(),
    }


def _source(
    kind: str,
    source: str,
    detail: str,
    *,
    authoritative: bool = False,
    record_count: int = 0,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "source": source,
        "kind": kind,
        "detail": detail,
        "authoritative": bool(authoritative),
        "record_count": int(record_count),
    }
    if note:
        entry["note"] = note
    return entry


def _db_source(table: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Provenance for rows read out of one table, taken from their own columns.

    ``provenance_authoritative`` is a claim the row makes about itself, so it is
    passed through rather than second-guessed -- but ``authoritative`` on the
    answer is true only when *every* row behind it claims that, so one
    non-authoritative row cannot let a mixed answer read as official.
    """
    authoritative = bool(rows) and all(bool(r.get("provenance_authoritative")) for r in rows)
    claimed = sorted({str(r.get("data_provenance")) for r in rows if r.get("data_provenance")})
    note = None
    if claimed:
        note = "rows declare data_provenance=" + ", ".join(claimed)
    return _source(
        "database",
        f"postgis:{table}",
        _DB_SOURCE_DETAIL.get(table, f"{table} table"),
        authoritative=authoritative,
        record_count=len(rows),
        note=note,
    )


def _demo_source(dataset: Dict[str, Any], record_count: int = 0) -> Dict[str, Any]:
    return _source(
        "demo-dataset",
        "app.pipelines.synthetic_generator",
        "generated Airoli demonstration dataset",
        authoritative=False,
        record_count=record_count,
        note="invented geometry and records; not a land record",
    )


def _opendata_source(regions: List[Dict[str, Any]], footprints: int) -> Dict[str, Any]:
    providers = sorted({str(r.get("source")) for r in regions if r.get("source")})
    note = None
    if providers:
        note = "served by " + ", ".join(providers)
    elif footprints == 0:
        note = "no area has been fetched into the registry yet"
    return _source(
        "open-data-registry",
        "app.opendata.service",
        "open-data area registry cache (footprints a configured provider returned)",
        # Every provider in the chain is either a government publication or
        # community/satellite data republished openly. Neither class is a
        # cadastral authority, so a cached footprint is never authoritative.
        authoritative=False,
        record_count=footprints,
        note=note,
    )


def _provenance(sources: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Roll a set of sources up into the provenance block every answer carries."""
    return {
        "sources": sources,
        "record_count": sum(int(s.get("record_count") or 0) for s in sources),
        "authoritative": bool(sources) and all(bool(s.get("authoritative")) for s in sources),
        "synthetic_included": any(
            s.get("kind") in ("demo-dataset", "simulated") for s in sources
        ),
    }


def _answer(
    category: str,
    filter_: Dict[str, Any],
    matched_ids: List[str],
    highlight: Dict[str, Any],
    explanation: str,
    source: str,
    limitations: List[str],
    provenance: Optional[Dict[str, Any]] = None,
    not_available: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Assemble one answer. Every path goes through here, so provenance and the
    not-available list cannot be forgotten by a branch that forgot them."""
    prov = provenance or _provenance([])
    return {
        "category": category,
        "filter": filter_,
        "matched_ids": matched_ids,
        "highlight": highlight,
        "explanation": explanation,
        "source": source,
        "limitations": limitations,
        "provenance": prov,
        "not_available": list(not_available or []),
        "synthetic": prov.get("synthetic_included", False),
    }


# --------------------------------------------------------------------------- #
# Geometry helpers                                                            #
# --------------------------------------------------------------------------- #


def _footprint_ring(ds: Dict[str, Any]) -> List[List[float]]:
    """Hero structure footprint as a coordinate ring.

    The dataset stores this as GeoJSON (a dict, or a JSON string depending on
    how the row was written), so normalise both shapes here rather than at each
    call site.
    """
    footprint = ds.get("hero_structure", {}).get("footprint_geojson")
    if not footprint:
        return []
    if isinstance(footprint, str):
        try:
            footprint = json.loads(footprint)
        except (ValueError, TypeError):
            return []
    if not isinstance(footprint, dict):
        return []
    geom_type = footprint.get("type")
    coords = footprint.get("coordinates") or []
    if geom_type == "Polygon" and coords:
        return coords[0]
    if geom_type == "MultiPolygon" and coords and coords[0]:
        return coords[0][0]
    return []


def _stored_ring(footprint: Any) -> List[List[float]]:
    """A stored footprint column (JSON text or dict) as a coordinate ring."""
    if isinstance(footprint, str):
        try:
            footprint = json.loads(footprint)
        except (ValueError, TypeError):
            return []
    return _footprint_ring({"hero_structure": {"footprint_geojson": footprint}})


def _ring_centroid(ring: List[List[float]]) -> Optional[List[float]]:
    try:
        return [float(v) for v in center_of(ring)]
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _hero_center(ds: Dict[str, Any]) -> Optional[List[float]]:
    """Footprint centroid in scene-local coordinates, or None if unavailable.

    Derived from the same footprint the 3D scene extrudes. The previous
    implementation returned a literal [160.0, 152.5, 9.0] that happened to match
    this centroid, so a footprint edit in the generator would have silently left
    the camera pointing at empty space while the answer still looked correct.
    """
    return _ring_centroid(_footprint_ring(ds))


def _hero_point(ds: Dict[str, Any]) -> Optional[List[float]]:
    """Focus point for the hero structure, at mid-height of its own footprint.

    Z is half the stored structure height so the camera lands on the middle of
    the mass rather than at ground level. Both components come from the dataset;
    if the dataset has no structure, None is returned and the caller highlights
    nothing rather than inventing a coordinate.
    """
    center = _hero_center(ds)
    if center is None:
        return None
    structure = ds.get("hero_structure", {})
    try:
        height = float(structure.get("height_m") or 0.0)
    except (TypeError, ValueError):
        height = 0.0
    return [center[0], center[1], round(height / 2.0, 2)]


def _stored_focus_point(row: Dict[str, Any]) -> Optional[List[float]]:
    """Focus point from a stored footprint, in whatever frame it is stored in.

    A row ingested from OpenStreetMap or GlobalML stores WGS84 degrees; a row
    written by the demo pipeline stores local metres. Which one this is cannot be
    told from the column, so the point is returned as stored and the caller
    labels the frame rather than pretending it is the scene frame. Guessing would
    send the camera somewhere the geometry is not.
    """
    ring = _stored_ring(row.get("footprint_geojson"))
    if not ring:
        return None
    center = _ring_centroid(ring)
    if center is None:
        return None
    try:
        z = float(row.get("ground_elevation_z") or 0.0) + float(row.get("height_m") or 0.0) / 2.0
    except (TypeError, ValueError):
        z = 0.0
    return [center[0], center[1], round(z, 2)]


# --------------------------------------------------------------------------- #
# Demo-dataset record readers                                                 #
# --------------------------------------------------------------------------- #


def _clashes(ds: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [o for o in ds.get("subsurface_objects", []) if o.get("has_clash")]


def _building_code_of(unit: Dict[str, Any]) -> str:
    """Owning building for a unit.

    Precinct units carry ``building_code``; the hero structure's units do not,
    but their proposed 3D id embeds it ("12345678901234/UB17-L02-201-X").
    """
    code = unit.get("building_code") or unit.get("structure_code")
    if code:
        return str(code)
    proposed = str(unit.get("proposed_3d_id", ""))
    if "B17" in proposed:
        return "B-17"
    return ""


def _mortgaged_units(ds: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Units whose rights record actually carries an active mortgage."""
    found = []
    # The hero structure's units and the surrounding precinct buildings are
    # stored separately, so both have to be scanned.
    units = list(ds.get("units", [])) + list(ds.get("all_precinct_units", []))
    for unit in units:
        number = unit.get("unit_number", "")
        for right in _rights_for(number, unit.get("unit_type", "U"), _building_code_of(unit)):
            if right.get("right_type") == "MORTGAGE" and right.get("encumbrance_status") == "ACTIVE":
                found.append({"unit": unit, "right": right})
                break
    return found


def _open_cases() -> List[Dict[str, Any]]:
    """Cases awaiting a decision, from the demo ledger.

    That ledger is a hardcoded list of two invented records held by the
    verification router, so the demo gate does not reach it on its own and it is
    gated here. With the gate shut those records must not surface in an answer as
    though a queue existed in front of an office: the real cases are read from
    the ``verification_cases`` table instead.
    """
    if not demo_mode_enabled():
        return []
    return [c for c in _CASES_DB if c.get("status") == "NEEDS_REVIEW"]


def _all_footprint_records(ds: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every record that can carry a footprint, across the dataset's shapes."""
    buildings = list(ds.get("precinct_buildings", []))
    structure = ds.get("hero_structure") or {}
    records: List[Dict[str, Any]] = list(buildings)
    if structure:
        records.append(structure)
    return records


# --------------------------------------------------------------------------- #
# Database record readers                                                     #
# --------------------------------------------------------------------------- #


def _db_structure_rows(index: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list((index.get("db") or {}).get("structures") or [])


def _row_label(row: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _parcel_answer(raw_text: str, text_query: str, index: Dict[str, Any]) -> Dict[str, Any]:
    """Answer a question about parcel records from the parcels table.

    Rows are named by ULPIN and labelled with the provenance each row declares,
    so a parcel ingested from OpenStreetMap cannot be read as a cadastral record
    simply by being in the same list as one that was.
    """
    if index.get("pinned"):
        return _no_match(raw_text, "PARCEL_RECORD_SEARCH", "a parcel record", index=index)
    rows = list((index.get("db") or {}).get("parcels") or [])
    if not rows:
        reason = (index.get("db_errors") or {}).get("parcels")
        return _answer(
            "PARCEL_RECORD_SEARCH",
            {"dataset_field": "parcels", "matched": False},
            [],
            _default_highlight(index),
            (
                "No parcel row is stored, so no parcel record can be reported. "
                "A parcel exists here only once something has ingested one."
            ),
            "postgis:parcels",
            ["No parcel rows are present. Nothing is described and nothing is highlighted."],
            provenance=_provenance([]),
            not_available=[_not_available("parcel_boundary")]
            + ([{"field": "parcels", "status": _NOT_AVAILABLE, "reason": reason}] if reason else []),
        )

    needle = text_query.strip().lower()
    matched = [r for r in rows if needle in str(r.get("ulpin", "")).lower()]
    if not matched:
        matched = rows
    sources = [_db_source("parcels", matched)]
    ids = [str(r.get("ulpin")) for r in matched if r.get("ulpin")]
    claimed = sorted({str(r.get("data_provenance")) for r in matched if r.get("data_provenance")})
    focus = None
    first = matched[0]
    focus = _stored_focus_point(first) or None
    parts = [
        f"{len(matched)} parcel row(s) are stored"
        + (f" (filtered to {len(matched)} matching {needle!r})" if len(matched) != len(rows) else "")
        + ": "
        + ", ".join(ids[:10])
        + ("." if len(ids) <= 10 else f", (+{len(ids) - 10} more).")
    ]
    parts.append(
        "Each row declares data_provenance="
        + (", ".join(claimed) if claimed else "unset")
        + "."
    )
    return _answer(
        "PARCEL_RECORD_SEARCH",
        {
            "dataset_field": "parcels",
            "queried": text_query.strip(),
            "data_provenance": claimed,
        },
        ids,
        _default_highlight(index, focus, frame="stored-geometry"),
        " ".join(parts),
        "postgis:parcels",
        [
            "These are rows in this deployment's database. A stored parcel row is "
            "not a certificate and nothing here was checked against a land registry.",
            "provenance_authoritative is the row's own claim about its source, "
            "passed through rather than verified.",
        ],
        provenance=_provenance(sources),
        not_available=[_not_available("parcel_boundary"), _not_available("title")],
    )


def _structure_answer(raw_text: str, text_query: str, index: Dict[str, Any]) -> Dict[str, Any]:
    """Answer a question about buildings from the structures table."""
    if index.get("pinned"):
        return _no_match(raw_text, "STRUCTURE_SOURCE_SEARCH", "a stored structure record", index=index)
    rows = _db_structure_rows(index)
    opendata = index.get("opendata") or {}
    regions = list(opendata.get("regions") or [])
    if not rows and not regions:
        return _answer(
            "STRUCTURE_SOURCE_SEARCH",
            {"dataset_field": "structures", "matched": False},
            [],
            _default_highlight(index),
            (
                "No building record is stored and no area has been fetched into the "
                "open-data registry, so no structure can be described. Buildings "
                "exist here only once a real provider has been read."
            ),
            "postgis:structures",
            ["Nothing is described and nothing is highlighted."],
            provenance=_provenance([]),
            not_available=[
                _not_available("permitted_fsi"),
                _not_available("approval_status"),
                _not_available("zoning"),
            ],
        )

    needle = text_query.strip().lower()
    matched = [
        r for r in rows
        if needle and needle in f"{r.get('building_code', '')} {r.get('name', '')}".lower()
    ] or rows
    sources = []
    if matched:
        sources.append(_db_source("structures", matched))
    if regions:
        sources.append(
            _opendata_source(regions, int(opendata.get("footprints") or 0))
        )
    ids = [_row_label(r, "building_code", "name") for r in matched][:10]
    ids = [i for i in ids if i]
    basis = sorted({str(r.get("height_basis")) for r in matched if r.get("height_basis")})
    # Where the geometry itself came from, which is a different claim from the
    # height basis above: a footprint lifted from Microsoft GlobalML or from
    # OpenStreetMap is a real published polygon, while one this codebase drew is
    # modelled, and a question about a building's source is answered by this
    # column rather than by the height's.
    extraction = sorted({str(r.get("extraction_source")) for r in matched if r.get("extraction_source")})
    parts = []
    if matched:
        parts.append(
            f"{len(matched)} structure row(s) are stored: {', '.join(ids[:10])}"
            + (f", (+{len(ids) - 10} more)." if len(ids) > 10 else ".")
        )
        parts.append(
            "Footprint extraction source recorded on those rows: "
            + (", ".join(extraction) if extraction else "unset")
            + "."
        )
        parts.append(
            "Height basis recorded on those rows: " + (", ".join(basis) if basis else "unset") + "."
        )
    if regions:
        served = ", ".join(
            f"{r.get('region')} from {r.get('source')} "
            f"({(r.get('counts') or {}).get('buildings', 0)} footprints)"
            for r in regions[:5]
        )
        parts.append(f"The open-data registry already holds {len(regions)} area(s): {served}.")
    else:
        unconfigured = opendata.get("providers_unconfigured") or []
        parts.append(
            "No area has been fetched into the open-data registry for this "
            "question"
            + (f"; providers not configured: {', '.join(unconfigured)}." if unconfigured else ".")
        )
    focus = _stored_focus_point(matched[0]) if matched else None
    return _answer(
        "STRUCTURE_SOURCE_SEARCH",
        {
            "dataset_field": "structures + open-data registry",
            "queried": text_query.strip(),
            # The two provenance columns are returned as data, not only prose: a
            # caller selecting by them needs the values, not a sentence.
            "extraction_sources": extraction,
            "height_bases": basis,
        },
        ids,
        _default_highlight(index, focus, frame="stored-geometry"),
        " ".join(parts),
        "postgis:structures",
        [
            "Footprint geometry is real where a provider published it and modelled "
            "where this codebase drew it; each row says which in data_provenance.",
            "Heights from OSM or GlobalML are frequently absent and are labelled "
            "modelled when they are derived. A height is not a survey.",
        ],
        provenance=_provenance(sources),
        not_available=[_not_available("permitted_fsi"), _not_available("approval_status")],
    )


def _submission_answer(raw_text: str, text_query: str, index: Dict[str, Any]) -> Dict[str, Any]:
    """Answer a question about submissions from the submissions table."""
    if index.get("pinned"):
        return _no_match(raw_text, "SUBMISSION_STATUS", "a stored submission", index=index)
    rows = list((index.get("db") or {}).get("submissions") or [])
    if not rows:
        reason = (index.get("db_errors") or {}).get("submissions")
        return _answer(
            "SUBMISSION_STATUS",
            {"dataset_field": "submissions", "matched": False},
            [],
            _default_highlight(index),
            "No submission row is stored, so no submission can be reported.",
            "postgis:submissions",
            ["Nothing is described and nothing is highlighted."],
            provenance=_provenance([]),
            not_available=[{"field": "submissions", "status": _NOT_AVAILABLE, "reason": reason}]
            if reason
            else [],
        )
    ids = [str(r.get("receipt_number")) for r in rows if r.get("receipt_number")]
    statuses: Dict[str, int] = {}
    for row in rows:
        key = str(row.get("status") or "unset")
        statuses[key] = statuses.get(key, 0) + 1
    breakdown = ", ".join(f"{count} {status}" for status, count in sorted(statuses.items()))
    return _answer(
        "SUBMISSION_STATUS",
        {"dataset_field": "submissions", "statuses": statuses},
        ids[:25],
        _default_highlight(index),
        (
            f"{len(rows)} submission row(s) are stored, by status: {breakdown}. "
            f"Receipts: {', '.join(ids[:10])}"
            + (f", (+{len(ids) - 10} more)." if len(ids) > 10 else ".")
        ),
        "postgis:submissions",
        [
            "A submission is a workflow row: a contributor filed it and a status "
            "was recorded against it. It is not an approval and no authority has "
            "accepted anything.",
        ],
        provenance=_provenance([_db_source("submissions", rows)]),
        not_available=[_not_available("approval_status")],
    )


def _boundary_answer(raw_text: str, text_query: str, index: Dict[str, Any]) -> Dict[str, Any]:
    """Answer a question about places from the admin_boundaries table."""
    if index.get("pinned"):
        return _no_match(raw_text, "ADMIN_BOUNDARY_SEARCH", "an administrative boundary", index=index)
    rows = list((index.get("db") or {}).get("admin_boundaries") or [])
    if not rows:
        reason = (index.get("db_errors") or {}).get("admin_boundaries")
        return _answer(
            "ADMIN_BOUNDARY_SEARCH",
            {"dataset_field": "admin_boundaries", "matched": False},
            [],
            _default_highlight(index),
            "No administrative boundary row is stored, so no place can be reported.",
            "postgis:admin_boundaries",
            ["Nothing is described and nothing is highlighted."],
            provenance=_provenance([]),
            not_available=[{"field": "admin_boundaries", "status": _NOT_AVAILABLE, "reason": reason}]
            if reason
            else [],
        )
    needle = text_query.strip().lower()
    matched = [
        r for r in rows
        if needle and (needle in str(r.get("name", "")).lower() or needle in str(r.get("code", "")).lower())
    ] or rows
    levels: Dict[str, int] = {}
    for row in matched:
        key = str(row.get("level") or "unset")
        levels[key] = levels.get(key, 0) + 1
    ids = [str(r.get("code")) for r in matched if r.get("code")]
    breakdown = ", ".join(f"{count} {level}" for level, count in sorted(levels.items()))
    sources = [_db_source("admin_boundaries", matched)]
    focus = None
    first = matched[0]
    if first.get("centroid_lat") is not None and first.get("centroid_lng") is not None:
        focus = [float(first["centroid_lng"]), float(first["centroid_lat"]), 0.0]
    return _answer(
        "ADMIN_BOUNDARY_SEARCH",
        {"dataset_field": "admin_boundaries", "levels": levels},
        ids[:25],
        _default_highlight(index, focus, frame="wgs84-centroid"),
        (
            f"{len(matched)} administrative boundary row(s) are stored, by level: "
            f"{breakdown}. Names: "
            + ", ".join(str(r.get('name')) for r in matched[:10])
            + (f", (+{len(matched) - 10} more)." if len(matched) > 10 else ".")
        ),
        "postgis:admin_boundaries",
        [
            "STATE and DISTRICT rows carry published geoBoundaries geometry. "
            "TALUKA and VILLAGE rows in this table are grid-synthesised "
            "subdivisions of a real parent, and each row's `source` column says so.",
            "A boundary in this table is a geometry record. It is not a revenue "
            "division's notification and no office issued it.",
        ],
        provenance=_provenance(sources),
    )


# --------------------------------------------------------------------------- #
# Answers that must refuse                                                    #
# --------------------------------------------------------------------------- #


def _registry_refusal(raw_text: str, category: str, fields: Tuple[str, ...]) -> Dict[str, Any]:
    """Refuse a question whose answer only a real registry could give.

    The fields listed are reported as ``not_available`` with the reason rather
    than left out, so a caller can tell which piece of their question has no
    source instead of receiving an empty answer and assuming the property has no
    title, no approval and no zone.
    """
    names = ", ".join(f.replace("_", " ") for f in fields)
    return _answer(
        category,
        {"dataset_field": list(fields), "matched": False, "status": _NOT_AVAILABLE},
        [],
        _default_highlight(None),
        (
            f"Not available: this deployment has no source for {names}. "
            + _unsourced_note(*fields)
            + " Nothing is matched, nothing is highlighted, and no value is estimated."
        ),
        "app.api.v1.ask_map:no-source",
        [
            "There is no configured registry, authority or publication that could "
            "answer this. An empty answer here is a gap in the sources, not a "
            "finding about the property.",
            "No value has been inferred, defaulted or carried over from generated "
            "data for any of the fields listed.",
        ],
        provenance=_provenance([]),
        not_available=[_not_available(f) for f in fields],
    )


# --------------------------------------------------------------------------- #
# Coverage and count answers                                                  #
# --------------------------------------------------------------------------- #


def _default_highlight(index: Optional[Dict[str, Any]], focus: Optional[List[float]] = None, *, frame: Optional[str] = None) -> Dict[str, Any]:
    """Neutral highlight: nothing selected, camera at the hero mass if we have one."""
    ds = (index or {}).get("dataset") or {}
    point = focus if focus is not None else _hero_point(ds)
    highlight: Dict[str, Any] = {
        "mode": "default",
        "highlight_color": "#64748B",
        "object_ids": [],
        "focus_point": point,
    }
    if frame:
        # The frame a stored point is in is not knowable from the column, so it
        # travels with the point rather than being assumed to be the scene's.
        highlight["focus_point_frame"] = frame
    return highlight


def _coverage_answer(raw_text: str, field: str, index: Dict[str, Any]) -> Dict[str, Any]:
    """Report how many records lack an optional attribute.

    Absence of a footprint or a height is a gap in what the records hold, not a
    finding about the building. OSM and GlobalML both omit height for the large
    majority of footprints, so "no height" is the normal case and saying so is
    more useful than pretending the value exists.
    """
    ds = index.get("dataset") or {}
    label = "footprint" if field == "footprint" else "height"
    keys = ("footprint_geojson", "footprint") if field == "footprint" else ("height_m", "height")
    records = _all_footprint_records(ds)

    missing: List[str] = []
    present = 0
    for record in records:
        has = any(record.get(k) not in (None, "", [], {}) for k in keys)
        if has:
            present += 1
        else:
            name = record.get("name") or record.get("building_code") or record.get("osm_id")
            missing.append(str(name) if name else "unnamed record")

    total = len(records)
    sources: List[Dict[str, Any]] = []
    if records and index.get("pinned"):
        return _coverage_from_records(
            raw_text, field, missing, present, total,
            _provenance([_demo_source(ds, total)]), index, records_only=True,
        )

    # A pinned record set is counted above and returned; from here the demo gate
    # decides whether generated records take part at all. Gating the records
    # rather than only the source entry keeps the denominator and the sources
    # from ever disagreeing about what was measured.
    if not index.get("demo_included"):
        records = []
        missing = []
        present = 0
        total = 0
    if total:
        sources.append(_demo_source(ds, total))
    # The same question against what the deployment really stores: a structure
    # row with no height is the same gap as a dataset record with no height.
    stored = _db_structure_rows(index)
    if stored:
        stored_missing = [
            _row_label(r, "building_code", "name") or "unnamed structure"
            for r in stored
            if any(r.get(k) not in (None, "", [], {}) for k in keys)
            is False
        ]
        sources.append(_db_source("structures", stored))
        regions = list((index.get("opendata") or {}).get("regions") or [])
        if regions:
            sources.append(
                _opendata_source(regions, int((index.get("opendata") or {}).get("footprints") or 0))
            )
        total += len(stored)
        missing.extend(stored_missing)
        present += len(stored) - len(stored_missing)
    else:
        regions = list((index.get("opendata") or {}).get("regions") or [])
        if regions:
            # Footprints in the registry are counted as present for this field:
            # a provider either returned a geometry ring or the record would not
            # exist at all.
            footprints = int((index.get("opendata") or {}).get("footprints") or 0)
            sources.append(_opendata_source(regions, footprints))
            total += footprints
            present += footprints

    if total == 0:
        return _no_match(raw_text, "COVERAGE_QUERY", f"any {label} data", index=index)
    return _coverage_from_records(
        raw_text, field, missing, present, total, _provenance(sources), index, records_only=False,
    )


def _coverage_from_records(
    raw_text: str,
    field: str,
    missing: List[str],
    present: int,
    total: int,
    provenance: Dict[str, Any],
    index: Dict[str, Any],
    *,
    records_only: bool,
) -> Dict[str, Any]:
    label = "footprint" if field == "footprint" else "height"
    kind = "footprints" if field == "footprint" else "height values"
    if not missing:
        explanation = f"All {total} record(s) carry a {label}."
    else:
        listed = ", ".join(missing[:8])
        more = f" (+{len(missing) - 8} more)" if len(missing) > 8 else ""
        explanation = (
            f"{len(missing)} of {total} record(s) have no {label}: "
            f"{listed}{more}. {present} do."
        )
    dataset_field = (
        "precinct_buildings + hero_structure"
        if records_only
        else "structures + open-data registry + demo dataset"
    )
    return _answer(
        "COVERAGE_QUERY",
        {"dataset_field": dataset_field, f"has_{label}": False},
        missing,
        _default_highlight(index),
        explanation,
        "app.pipelines.synthetic_generator:precinct_buildings" if records_only else "ask_map:records",
        [
            f"Missing {kind} is a gap in what these records hold. It is not evidence "
            "that a building is incomplete, unpermitted, or unmeasured in reality.",
            "Most real-world footprints in OSM and GlobalML carry no height at all, so "
            "this is the expected shape of the data rather than an anomaly.",
        ],
        provenance=provenance,
    )


def _count_answer(raw_text: str, text: str, index: Dict[str, Any]) -> Dict[str, Any]:
    """Answer a counting question, naming exactly what is being counted.

    Each group is counted separately and attributed separately: "14 buildings"
    means 14 rows in named tables and named footprints, not 14 buildings in the
    world.
    """
    ds = index.get("dataset") or {}
    buildings = ds.get("precinct_buildings", [])
    units = list(ds.get("units", [])) + list(ds.get("all_precinct_units", []))

    # Ordered narrowest-first: "how many buildings" must not be answered with a
    # unit count just because the word "units" appears in the explanatory tail.
    if "unit" in text or "flat" in text:
        subject = "units"
        dataset_count = len(units)
        db_table = None
    elif "footprint" in text:
        subject = "building footprints"
        dataset_count = sum(
            1
            for b in buildings
            if b.get("footprint_geojson") not in (None, "", [], {}) or b.get("footprint") not in (None, "", [], {})
        )
        db_table = "structures"
    else:
        subject = "buildings"
        dataset_count = len(buildings)
        db_table = "structures"

    db_rows = _db_structure_rows(index) if db_table else []
    regions = list((index.get("opendata") or {}).get("regions") or [])
    footprints = int((index.get("opendata") or {}).get("footprints") or 0)
    # The generated precinct joins the total only while the demo gate is open,
    # and it is dropped here rather than merely left out of the explanation: a
    # figure that counted rows the answer then refused to name would be a count
    # of something the reader cannot see.
    counted_demo = dataset_count if index.get("demo_included") else 0
    total = counted_demo + len(db_rows) + footprints

    if index.get("pinned"):
        if dataset_count == 0:
            return _no_match(raw_text, "COUNT_QUERY", f"any {subject}", index=index)
        return _answer(
            "COUNT_QUERY",
            {"dataset_field": "units" if subject == "units" else "precinct_buildings"},
            [],
            _default_highlight(index),
            f"The demo dataset holds {dataset_count} {subject}.",
            "app.pipelines.synthetic_generator",
            [
                "This counts rows in a synthetic dataset, not buildings or properties in "
                "the real world. The area is the invented demo precinct.",
            ],
            provenance=_provenance([_demo_source(ds, dataset_count)]),
        )

    if total == 0:
        return _no_match(raw_text, "COUNT_QUERY", f"any {subject}", index=index)

    sources: List[Dict[str, Any]] = []
    parts: List[str] = []
    if counted_demo:
        sources.append(_demo_source(ds, counted_demo))
        parts.append(f"{counted_demo} generated demo {subject}")
    if db_rows:
        sources.append(_db_source("structures", db_rows))
        parts.append(f"{len(db_rows)} stored structure row(s)")
    if footprints and regions:
        sources.append(_opendata_source(regions, footprints))
        served = ", ".join(sorted({str(r.get("source")) for r in regions if r.get("source")}))
        parts.append(f"{footprints} provider footprint(s) from {served or 'the open-data registry'}")

    limitations = [
        "This counts rows and cached footprints in named sources, not buildings or "
        "properties in the real world. Anything not ingested is not counted.",
    ]
    if counted_demo:
        limitations.append(
            "The generated demo precinct is included in that total and is invented data."
        )
    return _answer(
        "COUNT_QUERY",
        {"dataset_field": ", ".join(s["source"] for s in sources) or "none", "subject": subject},
        [],
        _default_highlight(index),
        (
            f"{total} {subject} across the sources this deployment holds: "
            + "; ".join(parts)
            + "."
        ),
        "ask_map:records",
        limitations,
        provenance=_provenance(sources),
    )


# --------------------------------------------------------------------------- #
# Routing                                                                     #
# --------------------------------------------------------------------------- #


def parse_query_deterministically(
    raw_text: str, dataset: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Route a question to a category, then answer it from the real records.

    Routing order is load-bearing, not incidental. The coverage and count
    questions were initially checked last, which made "how many are pending
    review" route to COUNT_QUERY and "buildings with no height" route to
    CHANGE_SEARCH -- both wrong, because "pending"/"review" and "height" are
    keywords of those other categories. Keyword overlap between allowlisted
    categories is inherent, so the more specific category is tested first: an
    explicit coverage/count phrase outranks the generic nouns, and a concrete
    noun ("clash", "mortgage", "floor") outranks a bare "how many".

    The new record-backed categories (parcel, structure, submission, boundary)
    sit after the five attribute categories and before the count, for the same
    reason: "how many villages" is a boundary question, and "how many buildings"
    is still a count.

    ``dataset`` is read once per call and threaded to every answer, because the
    routing branches below each scan it. Passing one pins the record set: the
    answer is built from exactly those records and neither the database nor the
    open-data registry is consulted, which is what makes a scenario reproducible
    and what makes an empty pinned set answer honestly. Callers may pass an
    explicit dataset to test a scenario; otherwise it is resolved here.
    """
    index = _resolve(dataset)
    ds = index.get("dataset") or {}
    text = raw_text.lower().strip()

    # Most specific first: these name an attribute to check, so they should not
    # be captured by "height" or "floor" in the change category below.
    if any(k in text for k in ("no footprint", "missing footprint", "without footprint",
                               "no height", "missing height", "without height")):
        field = "height" if "height" in text else "footprint"
        return _coverage_answer(raw_text, field, index)

    if any(k in text for k in ("clash", "underground", "pipe", "drainage", "subsurface", "utility")):
        return _underground_answer(raw_text, index)

    if any(k in text for k in ("mortgage", "bank", "loan", "lien", "encumbrance", "sbi")):
        return _rights_answer(raw_text, index)

    if any(k in text for k in ("change", "unauthorized", "floor", "additional", "height", "epoch")):
        return _change_answer(raw_text, index)

    # "How many" is a weak signal checked last of the attribute categories, so it
    # cannot swallow a concrete question. "how many are pending review" has to
    # reach the verification category, and it does because that test runs first.
    if any(k in text for k in ("pending", "review", "verification", "queue", "unverified")):
        return _verification_answer(raw_text, index)

    # ---- Record-backed categories -------------------------------------
    # Each names the table it reads, so a question that could be answered from a
    # parcel row is not answered from a generated dataset instead.
    if any(k in text for k in ("parcel", "plot", "survey number", "ulpin", "khasra",
                               "land record", "cadastral")):
        return _parcel_answer(raw_text, text, index)

    if any(k in text for k in ("submission", "submitted", "receipt", "declaration")):
        return _submission_answer(raw_text, text, index)

    if any(k in text for k in ("village", "district", "taluka", "tehsil", "boundary",
                               "jurisdiction", "state code", "place")):
        return _boundary_answer(raw_text, text, index)

    if any(k in text for k in ("structure", "building code", "building source",
                               "footprint source")):
        return _structure_answer(raw_text, text, index)

    # Categories whose only honest answer is a refusal. These sit after every
    # category that can return something, so a question that also asks about a
    # clash or a mortgage is still answered from those records -- and the missing
    # fields are reported on that answer too.
    if any(k in text for k in ("title", "ownership", "owner", "who owns", "registry",
                               "khata", "record of rights", "encumbrance certificate",
                               "mutation")):
        return _registry_refusal(raw_text, "REGISTRY_QUERY", ("title", "ownership"))

    if any(k in text for k in ("approval", "approved", "zoning", "zoned", "permitted",
                               "fsi", "compliance", "compliant", "legal", "illegal",
                               "lawful", "encroachment", "setback")):
        return _registry_refusal(
            raw_text, "COMPLIANCE_QUERY", ("approval_status", "zoning", "permitted_fsi")
        )

    # Count questions last: "how many" is a weak signal and would otherwise
    # swallow a concrete question that happens to start with it, as in "how
    # many are pending review", which is a verification query.
    if any(k in text for k in ("how many", "count of", "total number")):
        return _count_answer(raw_text, text, index)

    # No category matched, so no record scan ran. Report that honestly and
    # highlight nothing rather than pointing at an arbitrary parcel.
    return _no_match(raw_text, "PROPERTY_SEARCH", "a supported query category", index=index)


# --------------------------------------------------------------------------- #
# Attribute-category answers, over every layer                                #
# --------------------------------------------------------------------------- #


def _pinned_nothing_matched(
    raw_text: str,
    category: str,
    described: str,
    index: Dict[str, Any],
    found: bool,
) -> Optional[Dict[str, Any]]:
    """The answer when a pinned record set holds nothing for this category.

    A caller that pins a record set has said those records are the whole world
    for this question. When they hold nothing, the honest answer is "nothing
    matched in the records you pinned" -- not a message about what "this
    deployment" contains, because the deployment was never consulted here and
    cannot be described from a record set that excludes it. The unpinned path
    keeps its own wording, since there the deployment really is what was
    searched and its absences are worth stating one by one.

    Returns ``None`` when the answer is not this one, so each caller reads as a
    single guard clause rather than a branch threaded through its own logic.
    """
    if index.get("pinned") and not found:
        return _no_match(raw_text, category, described, index=index)
    return None


def _underground_answer(raw_text: str, index: Dict[str, Any]) -> Dict[str, Any]:
    """Subsurface clash search across stored spatial units and the demo dataset."""
    ds = index.get("dataset") or {}
    clashes = _clashes(ds)
    empty = _pinned_nothing_matched(
        raw_text, "UNDERGROUND_CLASH_SEARCH", "a recorded subsurface clash", index, bool(clashes)
    )
    if empty is not None:
        return empty
    db_rows = list((index.get("db") or {}).get("spatial_units") or []) if not index.get("pinned") else []
    sources: List[Dict[str, Any]] = []
    if clashes:
        sources.append(_demo_source(ds, len(clashes)))
    if db_rows:
        sources.append(_db_source("spatial_units", db_rows))

    ids: List[str] = []
    notes: List[str] = []
    focus: Optional[List[float]] = None
    if clashes:
        primary = clashes[0]
        ids.extend(c["code"] for c in clashes if c.get("code"))
        start = (primary.get("geometry_3d") or {}).get("start")
        if isinstance(start, list) and len(start) >= 3:
            try:
                focus = [float(start[0]), float(start[1]), float(start[2])]
            except (TypeError, ValueError):
                focus = None
        note = (primary.get("mitigation_note") or "").strip()
        if note:
            notes.append(f"Dataset note: {note}")
    if db_rows:
        ids.extend(str(r.get("code")) for r in db_rows if r.get("code"))
        clash_note = next(
            (str(r.get("clash_details")) for r in db_rows if r.get("clash_details")), None
        )
        if clash_note:
            notes.append(f"Stored note: {clash_note}")
    if focus is None:
        focus = _hero_point(ds)

    if not ids:
        reasons = [f for f in ("spatial_units",) if (index.get("db_errors") or {}).get(f)]
        return _answer(
            "UNDERGROUND_CLASH_SEARCH",
            {"dataset_field": "spatial_units + subsurface_objects", "has_clash": True, "matched": False},
            [],
            _default_highlight(index),
            (
                "No subsurface object in this deployment is recorded as clashing. "
                "Buried-asset geometry is only held where a source publishes it, "
                "which for India is OpenStreetMap and very little of it."
            ),
            "ask_map:records",
            [
                "An empty result here means nothing is mapped, not that nothing is "
                "buried. No underground utility dataset is published for India.",
            ],
            provenance=_provenance(sources),
            not_available=[{"field": "spatial_units", "status": _NOT_AVAILABLE, "reason": r} for r in reasons],
        )

    parts = [
        f"{len(ids)} subsurface object(s) are recorded as clashing: " + ", ".join(ids[:12]) + "."
    ]
    parts.extend(notes)
    return _answer(
        "UNDERGROUND_CLASH_SEARCH",
        {"dataset_field": "spatial_units + subsurface_objects", "has_clash": True},
        ids,
        {
            "mode": "underground",
            "highlight_color": "#EF4444",
            "object_ids": ids,
            "focus_point": focus,
        },
        " ".join(parts),
        "ask_map:records",
        [
            "A flagged clash is a geometry conflict between two records. It is not a "
            "confirmed engineering defect and not a statutory clearance breach.",
            "No underground utility network is published for India, so the absence of "
            "clashes here is an absence of mapping.",
        ],
        provenance=_provenance(sources),
    )


def _rights_answer(raw_text: str, index: Dict[str, Any]) -> Dict[str, Any]:
    """Active encumbrances across stored rights rows and the simulated set."""
    ds = index.get("dataset") or {}
    mortgaged = _mortgaged_units(ds)
    empty = _pinned_nothing_matched(
        raw_text, "RIGHTS_SEARCH", "a recorded active mortgage", index, bool(mortgaged)
    )
    if empty is not None:
        return empty
    db_rows = list((index.get("db") or {}).get("rights") or []) if not index.get("pinned") else []
    mortgages = [
        r for r in db_rows
        if str(r.get("right_type", "")).upper() == "MORTGAGE"
    ] if db_rows else []
    # Rows carrying their own "this is simulated" flag are reported as simulated,
    # not counted as a real lien, wherever they are matched from.
    synthetic_rows = [r for r in mortgages if r.get("is_synthetic")]
    sources: List[Dict[str, Any]] = []
    if mortgaged:
        sources.append(
            _source(
                "simulated",
                "app.scene.scene_architect:_rights_for",
                "simulated rights attached to the demonstration dataset",
                authoritative=False,
                record_count=len(mortgaged),
                note="exercises the rights layer; it is not a lien",
            )
        )
    if mortgages:
        sources.append(_db_source("rights", mortgages))

    ids = [m["unit"].get("proposed_3d_id", m["unit"].get("unit_number", "?")) for m in mortgaged]
    parts: List[str] = []
    if mortgaged:
        by_right: Dict[tuple, Dict[str, List[str]]] = {}
        for m in mortgaged:
            right = m["right"]
            key = (right.get("party_name"), right.get("mortgage_amount_inr"))
            numbers = by_right.setdefault(key, {}).setdefault(str(m["unit"].get("unit_number")), [])
            building = m["unit"].get("building_code") or m["unit"].get("structure_code")
            if building:
                numbers.append(str(building))
        for (party, amount), numbers_by_unit in by_right.items():
            amount_text = f"INR {amount:,.0f}" if isinstance(amount, (int, float)) else "an unspecified amount"
            where = "; ".join(
                f"flat {number} in {len(bs)} building(s)" if len(bs) > 1 else f"flat {number}"
                for number, bs in sorted(numbers_by_unit.items())
            )
            parts.append(
                f"{len(mortgaged)} unit(s) carry a simulated MORTGAGE right held by {party} "
                f"for {amount_text}: {where}."
            )
    if mortgages:
        ids.extend(str(r.get("proposed_3d_id") or r.get("unit_number")) for r in mortgages)
        detail = ", ".join(
            f"unit {r.get('unit_number') or r.get('proposed_3d_id')}"
            + (f" held by {r['party_name']}" if r.get("party_name") else "")
            + (
                f" for INR {float(r['mortgage_amount_inr']):,.0f}"
                if isinstance(r.get("mortgage_amount_inr"), (int, float))
                else ""
            )
            + (" [row flagged synthetic]" if r.get("is_synthetic") else "")
            for r in mortgages[:10]
        )
        lead = (
            f"{len(mortgages)} stored rights row(s) record an active MORTGAGE"
            + (f", {len(synthetic_rows)} of them flagged is_synthetic" if synthetic_rows else "")
            + f": {detail}."
        )
        parts.insert(0, lead)

    if not parts:
        reasons = [f for f in ("rights",) if (index.get("db_errors") or {}).get(f)]
        return _answer(
            "RIGHTS_SEARCH",
            {"dataset_field": "rights", "right_type": "MORTGAGE", "matched": False},
            [],
            _default_highlight(index),
            (
                "No active mortgage is recorded in this deployment, and no registry "
                "of encumbrances has been consulted to find one."
            ),
            "ask_map:records",
            [
                "An empty result is not a clean title. Nothing here has been checked "
                "against a record of rights, so the absence of a recorded lien here "
                "proves nothing about a real property.",
            ],
            provenance=_provenance(sources),
            not_available=(
                [_not_available("title"), {"field": "rights", "status": _NOT_AVAILABLE, "reason": reasons[0]}]
                if reasons
                else [_not_available("title")]
            ),
        )

    return _answer(
        "RIGHTS_SEARCH",
        {
            "dataset_field": "rights + unit rights",
            "right_type": "MORTGAGE",
            "encumbrance_status": "ACTIVE",
        },
        [i for i in ids if i],
        {
            "mode": "rights",
            "highlight_color": "#EF4444",
            "object_ids": [i for i in ids if i],
            "focus_point": _hero_point(ds),
        },
        " ".join(parts),
        "ask_map:records",
        [
            "A stored or simulated encumbrance is a row, not a registered lien. "
            "No registry of any kind was consulted and no real lien is asserted.",
            "Rows flagged is_synthetic exercise the rights layer and are not claims "
            "about any real property.",
        ],
        provenance=_provenance(sources),
        not_available=[_not_available("title")],
    )


def _change_answer(raw_text: str, index: Dict[str, Any]) -> Dict[str, Any]:
    """Inter-epoch differences from stored change rows and the demo dataset."""
    ds = index.get("dataset") or {}
    change = ds.get("epoch2_change") or {}
    empty = _pinned_nothing_matched(
        raw_text, "CHANGE_SEARCH", "a recorded inter-epoch difference", index, bool(change)
    )
    if empty is not None:
        return empty
    db_rows = list((index.get("db") or {}).get("property_changes") or []) if not index.get("pinned") else []
    sources: List[Dict[str, Any]] = []
    ids: List[str] = []
    parts: List[str] = []

    if change:
        sources.append(_demo_source(ds, 1))
        added = change.get("added_units") or []
        added_ids = [u.get("proposed_3d_id") for u in added if u.get("proposed_3d_id")]
        ids.extend(i for i in added_ids if i)
        parts.append(
            f"The demo dataset records a difference between {change.get('epoch_from')} and "
            f"{change.get('epoch_to')}: +{change.get('delta_height_m')} m over "
            f"{change.get('delta_floors')} floor, reaching {change.get('new_floor_count')} floors, "
            f"with units {', '.join(str(u.get('unit_number')) for u in added) or 'none listed'} "
            "present only in the later epoch."
        )
    if db_rows:
        sources.append(_db_source("property_changes", db_rows))
        for row in db_rows[:10]:
            parts.append(
                f"A stored change row records {row.get('change_type')} from "
                f"{row.get('epoch_from')} to {row.get('epoch_to')}: status "
                f"{row.get('status')!r}, +{row.get('delta_height_m')} m / "
                f"+{row.get('delta_floors')} floor(s)."
            )
        ids.extend(f"change:{r.get('change_type')}" for r in db_rows[:10])

    if not parts:
        reasons = [f for f in ("property_changes",) if (index.get("db_errors") or {}).get(f)]
        return _answer(
            "CHANGE_SEARCH",
            {"dataset_field": "property_changes", "matched": False},
            [],
            _default_highlight(index),
            (
                "No inter-epoch difference is recorded in this deployment. Nothing "
                "establishes that any change happened, or that one was unauthorised."
            ),
            "ask_map:records",
            [
                "A change question cannot be answered without two dated observations "
                "of the same structure, and this deployment holds none.",
            ],
            provenance=_provenance(sources),
            not_available=[_not_available("change_authorisation")]
            + [{"field": "property_changes", "status": _NOT_AVAILABLE, "reason": r} for r in reasons],
        )

    return _answer(
        "CHANGE_SEARCH",
        {
            "dataset_field": "property_changes + epoch2_change",
            "epoch_from": (db_rows[0] if db_rows else change).get("epoch_from"),
            "epoch_to": (db_rows[0] if db_rows else change).get("epoch_to"),
        },
        ids or ["B-17"],
        {
            "mode": "time_slider",
            "highlight_color": "#F59E0B",
            "object_ids": ids or ["B-17"],
            "focus_point": _hero_point(ds),
        },
        " ".join(parts),
        "ask_map:records",
        [
            "This is a difference between two dated records, not a determination "
            "that anything was unauthorised. No authority has been asked, and no "
            "permission or sanction has been read.",
        ],
        provenance=_provenance(sources),
        not_available=[_not_available("change_authorisation")],
    )


def _verification_answer(raw_text: str, index: Dict[str, Any]) -> Dict[str, Any]:
    """Records awaiting a decision, from the stored cases and the demo ledger."""
    ds = index.get("dataset") or {}
    cases = _open_cases()
    empty = _pinned_nothing_matched(
        raw_text, "VERIFICATION_STATUS", "a record awaiting a decision", index, bool(cases)
    )
    if empty is not None:
        return empty
    db_rows = list((index.get("db") or {}).get("verification_cases") or []) if not index.get("pinned") else []
    sources: List[Dict[str, Any]] = []
    if cases:
        sources.append(_demo_source(ds, len(cases)))
    if db_rows:
        sources.append(_db_source("verification_cases", db_rows))

    ids: List[str] = []
    parts: List[str] = []
    focus_ids: List[str] = []
    if cases:
        ids.extend(c["case_number"] for c in cases)
        focus_ids.extend(c.get("parcel_ulpin") for c in cases if c.get("parcel_ulpin"))
        parts.append(
            f"{len(cases)} record(s) have status NEEDS_REVIEW: "
            + ", ".join(f"{c['case_number']} ({c.get('case_type')})" for c in cases)
            + ". No officer decision has been recorded against them."
        )
    if db_rows:
        ids.extend(str(r.get("case_number")) for r in db_rows if r.get("case_number"))
        focus_ids.extend(str(r.get("parcel_ulpin")) for r in db_rows if r.get("parcel_ulpin"))
        parts.append(
            f"{len(db_rows)} stored verification case(s) await a decision: "
            + ", ".join(
                f"{r.get('case_number')} ({r.get('case_type')}, {r.get('status')})"
                for r in db_rows[:10]
            )
            + "."
        )

    if not parts:
        reasons = [f for f in ("verification_cases",) if (index.get("db_errors") or {}).get(f)]
        return _answer(
            "VERIFICATION_STATUS",
            {"dataset_field": "verification_cases", "status": "NEEDS_REVIEW", "matched": False},
            [],
            _default_highlight(index),
            (
                "No record is awaiting a decision in this deployment. No officer, "
                "reviewer or authority is involved and nothing is pending anywhere."
            ),
            "ask_map:records",
            ["These are workflow rows, not a real queue in front of any office."],
            provenance=_provenance(sources),
            not_available=[{"field": "verification_cases", "status": _NOT_AVAILABLE, "reason": r} for r in reasons],
        )

    return _answer(
        "VERIFICATION_STATUS",
        {
            "dataset_field": "verification_cases + demo cases",
            "status": "NEEDS_REVIEW",
        },
        [i for i in ids if i],
        {
            "mode": "verification",
            "highlight_color": "#F59E0B",
            "object_ids": [i for i in focus_ids if i],
            "focus_point": _hero_point(ds),
        },
        " ".join(parts),
        "ask_map:records",
        [
            "These are workflow rows in this deployment. No government officer or "
            "authority is involved, and a NEEDS_REVIEW status is a row state rather "
            "than a finding.",
        ],
        provenance=_provenance(sources),
    )


def _no_match(
    raw_text: str,
    category: str,
    described: str,
    *,
    index: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Report an honest empty result instead of inventing a match."""
    index = index if index is not None else {"dataset": {}}
    # The wording names what was actually searched: a pinned dataset is the demo
    # dataset, and saying so is what makes an empty pinned set a testable,
    # honest "nothing matched" rather than a hint that somewhere else might have
    # an answer.
    scope = "the demo dataset" if index.get("pinned") else "the records this deployment holds"
    source = "app.pipelines.synthetic_generator" if index.get("pinned") else "ask_map:records"
    return _answer(
        category,
        {"dataset_field": described, "matched": False},
        [],
        _default_highlight(index),
        (
            f"No record in {scope} matches {described}. "
            "Supported categories are underground clashes, mortgages and "
            "encumbrances, inter-epoch changes, records awaiting a decision, "
            "parcels, structures, submissions and administrative boundaries. "
            "Nothing is highlighted."
        ),
        source,
        [
            "Only records this deployment actually stores or has fetched are "
            "searched; it is not a searchable register of any real property.",
            "Routing is keyword-based, so a rephrased question may not match a category.",
        ],
        provenance=_provenance([]),
    )


@router.post("/ask", response_model=AskMapResult)
def ask_map(req: AskMapQuery):
    """Answer a natural-language question from the records this deployment holds.

    Every answer carries the provenance of the rows it matched and reports, per
    field, anything no real source covers as ``NOT_AVAILABLE`` rather than
    filling it in.
    """
    t0 = time.perf_counter()
    parsed = parse_query_deterministically(req.query)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    provenance = parsed.get("provenance") or _provenance([])
    synthetic = bool(provenance.get("synthetic_included"))
    return AskMapResult(
        query=req.query,
        intent_category=parsed["category"],
        matched_filter=parsed["filter"],
        matched_entity_ids=parsed["matched_ids"],
        highlight_3d=parsed["highlight"],
        human_explanation=parsed["explanation"],
        execution_time_ms=elapsed_ms,
        match_count=len(parsed["matched_ids"]),
        data_source=parsed["source"],
        synthetic=synthetic,
        limitations=parsed["limitations"],
        disclaimer=_SYNTHETIC_DISCLAIMER if synthetic else _STORED_RECORD_DISCLAIMER,
        provenance=provenance,
        not_available=parsed.get("not_available") or [],
    )