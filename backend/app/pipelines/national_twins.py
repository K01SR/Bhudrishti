"""
National 3D twin extrusion - persisted digital twins for every national parcel.

Uses the *real* georeferenced parcel geometry (EPSG:4326 stored in
``national_parcels``). Each parcel is transformed into ITS OWN UTM zone (not
the fixed UTM 43 of the Airoli demo) so NBC 2016 setbacks and footprint
geometry are geographically accurate anywhere in India, then the resulting
twin is persisted to ``national_twins`` with the footprint re-projected back to
EPSG:4326 (so tiles/visualization can consume it directly).

Idempotent: upsert by ``ulpin``. ``force=True`` re-extrudes and updates.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from pyproj import Transformer
from shapely.geometry import Polygon, mapping
from geoalchemy2.shape import to_shape
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.id_engine.extruder import extrude_parcel_to_3d_twin, get_next_available_building_code
from app.models.boundary import AdminBoundary
from app.models.national_parcel import NationalParcel
from app.models.national_twin import NationalTwin
from app.pipelines.boundary_ingest import _utm_epsg

log = logging.getLogger(__name__)

# NBC 2016 statutory setbacks (Table 3) by building height class.
NBC_SETBACKS_M = {
    "LOW_RISE": 3.0,        # up to 15 m
    "MID_RISE": 6.0,        # 15-24 m
    "HIGH_RISE": 9.0,       # 24-36 m
    "TALL": 15.0,           # > 36 m
}


def _utm_epsg_for_parcel(parcel: NationalParcel) -> int:
    lng = parcel.centroid_lng if parcel.centroid_lng is not None else 77.0
    return _utm_epsg(lng)


def _parcel_local_ring(parcel: NationalParcel) -> List[List[float]]:
    """Real parcel ring transformed to its own UTM metre frame (ccw, closed)."""
    g = to_shape(parcel.geom)
    epsg = _utm_epsg_for_parcel(parcel)
    to_p = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    ring = [to_p.transform(x, y) for x, y in list(g.exterior.coords)]
    return [[round(x, 3), round(y, 3)] for x, y in ring]


def _footprint_back_to_4326(fp_coords: List[List[float]], epsg: int) -> Dict[str, Any]:
    """Re-projects the extruded footprint metre ring back to EPSG:4326 GeoJSON."""
    to_g = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    ring = [[to_g.transform(x, y)[0], to_g.transform(x, y)[1]] for x, y in fp_coords]
    return {"type": "Polygon", "coordinates": [ring]}


def _nbc_setback_for_height(height_m: float) -> float:
    if height_m > 36:
        return NBC_SETBACKS_M["TALL"]
    if height_m > 24:
        return NBC_SETBACKS_M["HIGH_RISE"]
    if height_m > 15:
        return NBC_SETBACKS_M["MID_RISE"]
    return NBC_SETBACKS_M["LOW_RISE"]


def extrude_national_parcel(
    db: Session,
    ulpin: str,
    *,
    force: bool = False,
    custom_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Builds + persists a 3D twin for one national parcel using its real geometry."""
    parcel = db.execute(
        select(NationalParcel).where(NationalParcel.ulpin == ulpin.upper())
    ).scalar_one_or_none()
    if parcel is None:
        raise ValueError(f"No national parcel with ULPIN '{ulpin}'.")

    existing = db.execute(
        select(NationalTwin).where(NationalTwin.ulpin == parcel.ulpin)
    ).scalar_one_or_none()
    was_fresh = existing is None
    if existing is not None and not force:
        return {"status": "ALREADY_EXISTS", "ulpin": parcel.ulpin, "twin_id": existing.id}

    local_ring = _parcel_local_ring(parcel)
    epsg = _utm_epsg_for_parcel(parcel)

    parcel_dict = {
        "ulpin": parcel.ulpin,
        "survey_number": parcel.survey_number,
        "polygon_geojson": {"type": "Polygon", "coordinates": [local_ring]},
        "calculated_area_m2": parcel.area_m2 or 1000.0,
        "document_area_m2": parcel.area_m2 or 1000.0,
        "location": {
            "state": parcel.state_code,
            "district": parcel.district_code,
            "village_ward": parcel.boundary_code,
        },
    }

    # Deterministic building index from the ULPIN (Python hash() is per-process random).
    build_idx = sum(ord(c) for c in parcel.ulpin) % 7

    custom = dict(custom_params or {})
    custom.setdefault("code", f"NP-{parcel.survey_number or parcel.ulpin[-4:]}")

    try:
        twin = extrude_parcel_to_3d_twin(parcel_dict, building_idx=build_idx, custom_params=custom)
    except Exception as exc:  # noqa: BLE001
        log.warning("extrude failed for %s: %s", parcel.ulpin, exc)
        raise ValueError(f"Extrusion failed: {exc}")

    fp_coords = twin.get("footprint_coords")
    if not fp_coords:
        fp_coords = twin.get("footprint_geojson", {}).get("coordinates", [[]])[0]

    height_m = float(twin.get("height_m") or twin.get("total_height_m") or 0.0)
    setback = _nbc_setback_for_height(height_m) if height_m else 3.0
    fp_4326 = _footprint_back_to_4326(fp_coords, epsg)

    units_summary = [
        {
            "proposed_3d_id": u.get("proposed_3d_id"),
            "level_code": u.get("level_code"),
            "unit_type": u.get("unit_type"),
            "carpet_area_m2": u.get("carpet_area_m2"),
        }
        for u in twin.get("units", [])[:20]
    ]

    if existing is None:
        existing = NationalTwin(ulpin=parcel.ulpin)
        db.add(existing)

    existing.boundary_code = parcel.boundary_code
    existing.state_code = parcel.state_code
    existing.survey_number = parcel.survey_number
    existing.structure_code = twin.get("code", "B-000")
    existing.name = twin.get("name")
    existing.typology = twin.get("type")
    existing.structure_type = twin.get("structure_type")
    existing.footprint_polygon = f"SRID=4326;{Polygon(fp_4326['coordinates'][0]).wkt}"
    existing.footprint_polygon_geojson = fp_4326
    existing.plot_area_m2 = parcel.area_m2
    existing.setback_m = setback
    existing.buildable_area_m2 = float(twin.get("fp_area") or twin.get("footprint_area_m2") or 0.0)
    existing.footprint_area_m2 = float(twin.get("fp_area") or twin.get("footprint_area_m2") or 0.0)
    existing.floors = int(twin.get("floors") or 0)
    existing.floor_height_m = float(twin.get("floor_h") or 0.0)
    existing.height_m = height_m
    existing.built_up_area_m2 = float(twin.get("built_up_area") or 0.0)
    existing.fsi = float(twin.get("fsi") or 0.0)
    existing.fsi_status = twin.get("fsi_status")
    existing.proposed_3d_id = twin.get("proposed_3d_id")
    existing.units_count = len(twin.get("units", []))
    existing.units_summary = units_summary
    existing.twin = twin
    existing.provenance = {
        "source": "Synthesized 3D Extrusion (NBC 2016)",
        "authoritative": False,
        "is_synthetic": True,
        "setback_rule": "NBC 2016 Table 3",
    }

    db.commit()

    return {
        "status": "RE-EXTRUDED" if not was_fresh else "SUCCESS",
        "ulpin": parcel.ulpin,
        "survey_number": parcel.survey_number,
        "boundary_code": parcel.boundary_code,
        "twin_id": existing.id,
        "structure_code": existing.structure_code,
        "proposed_3d_id": existing.proposed_3d_id,
        "height_m": existing.height_m,
        "floors": existing.floors,
        "fsi": existing.fsi,
        "fsi_status": existing.fsi_status,
        "setback_m": setback,
        "footprint_area_m2": existing.footprint_area_m2,
        "units_count": existing.units_count,
    }


def extrude_parcels_for_boundary(
    db: Session,
    boundary_code: str,
    *,
    limit: int = 100,
    force: bool = False,
) -> Dict[str, Any]:
    """Extrudes all national parcels currently synthesized within a boundary."""
    parcels = db.execute(
        select(NationalParcel)
        .where(NationalParcel.boundary_code == boundary_code)
        .limit(limit)
    ).scalars().all()

    results = []
    errors = []
    for p in parcels:
        try:
            results.append(extrude_national_parcel(db, p.ulpin, force=force))
        except (ValueError, Exception) as exc:  # noqa: BLE001
            errors.append({"ulpin": p.ulpin, "error": str(exc)})

    return {
        "boundary_code": boundary_code,
        "parcels_scanned": len(parcels),
        "twins_created": sum(1 for r in results if r["status"] == "SUCCESS"),
        "twins_reextruded": sum(1 for r in results if r["status"] == "RE-EXTRUDED"),
        "already_exists": sum(1 for r in results if r["status"] == "ALREADY_EXISTS"),
        "errors": errors,
        "twins": results,
    }


def get_twin_detail(db: Session, ulpin: str) -> Optional[Dict[str, Any]]:
    """Returns the persisted twin for a national parcel ULPIN."""
    t = db.execute(
        select(NationalTwin).where(NationalTwin.ulpin == ulpin.upper())
    ).scalar_one_or_none()
    if t is None:
        return None
    return {
        "ulpin": t.ulpin,
        "survey_number": t.survey_number,
        "boundary_code": t.boundary_code,
        "structure_code": t.structure_code,
        "name": t.name,
        "typology": t.typology,
        "height_m": t.height_m,
        "floors": t.floors,
        "setback_m": t.setback_m,
        "footprint_area_m2": t.footprint_area_m2,
        "built_up_area_m2": t.built_up_area_m2,
        "fsi": t.fsi,
        "fsi_status": t.fsi_status,
        "fsi_status_reason": t.fsi_status_reason,
        "provenance": t.provenance or {
            "source": "Synthesized 3D Twin",
            "authoritative": False,
            "is_synthetic": True,
        },
        "proposed_3d_id": t.proposed_3d_id,
        "units_count": t.units_count,
        "units_summary": t.units_summary,
        "footprint_polygon": t.footprint_polygon_geojson,
    }