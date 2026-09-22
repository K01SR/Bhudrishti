"""
National parcel synthesis + ULPIN derivation (Phase 2 - engine-first).

Every real village boundary (from the geoBoundaries-seeded ``admin_boundaries``
table) is deterministically subdivided into a handful of parcels on the same
projected grid used for taluka/village synthesis. Each parcel keeps its real
EPSG:4326 polygon and receives a georeferenced 14-char ULPIN via the
Bhu-Aadhaar-aligned engine (``national.py``), so the whole country resolves
parcel identifiers without any external ULPIN API.

The derivation is *deterministic and idempotent*: re-running over the same
village reproduces the same grid and the same ULPINs (upsert by ULPIN).
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import Polygon
from shapely.validation import make_valid
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.id_engine.national import parcel_ulpin_from_vertices
from app.models.boundary import AdminBoundary
from app.models.national_parcel import NationalParcel
from app.pipelines.boundary_ingest import _utm_epsg, _grid_split, _centroid_latlng, _norm_code

log = logging.getLogger(__name__)

MAX_PARCELS_PER_VILLAGE = int(__import__("os").getenv("MAX_PARCELS_PER_VILLAGE", "6"))
SYNTH_LEVELS = ("VILLAGE", "TALUKA")


def _shapely_of(row: AdminBoundary) -> Any:
    """Converts an AdminBoundary's stored geometry to a shapely geometry."""
    from geoalchemy2.shape import to_shape
    from shapely.geometry import shape

    try:
        return make_valid(to_shape(row.geom))
    except Exception:
        return make_valid(shape(row.geom))


def _ring_of(geom: Any) -> List[Tuple[float, float]]:
    """Outer ring of a valid polygon as (lat, lon) pairs, traversed CW."""
    from shapely.geometry import shape

    g = make_valid(shape(geom.__geo_interface__))
    if g.geom_type == "Polygon":
        ring = g.exterior
    elif g.geom_type == "MultiPolygon":
        ring = max(g.geoms, key=lambda p: p.area).exterior
    else:
        raise ValueError(f"unsupported geometry type: {g.geom_type}")
    pts = list(ring.coords)
    # return as [lat, lon] pairs, drop repeated closing vertex for derivation
    return [(round(float(y), 6), round(float(x), 6)) for x, y in pts[:-1]]


def _survey_number(idx: int, offset: int) -> str:
    """Deterministic survey number for a parcel inside its village."""
    return f"{offset + idx + 1:06d}"


def _zonal_class(geom: Any, idx: int) -> str:
    """Deterministic zoning: AGRI ring around the boundary, then RESIDENTIAL."""
    return "AGRI" if idx == 0 else "RESIDENTIAL"


def _coerce_polygon(cell: Any) -> Any:
    """Returns the largest Polygon component (column type is POLYGON, not MULTI)."""
    if cell.geom_type == "MultiPolygon":
        return max(cell.geoms, key=lambda p: p.area)
    return cell


def _metric_area_m2(cell: Any) -> float:
    """Signed metric area (m²) via local UTM projection of the lat/lon polygon."""
    from pyproj import Transformer

    cx = cell.centroid.x
    try:
        to_p = Transformer.from_crs("EPSG:4326", f"EPSG:{_utm_epsg(cx)}", always_xy=True)
    except Exception:
        return float(round(cell.area * (111.32 ** 2), 3))
    try:
        from shapely.ops import transform

        proj = transform(lambda x, y: to_p.transform(x, y), cell)
        import math
        area = abs(proj.area)
        return float(round(area, 3))
    except Exception:
        return float(round(cell.area * (111.32 ** 2), 3))


def _derive_for_cell(
    cell: Any,
    idx: int,
) -> Tuple[str, Dict[str, Any], Optional[str], float, float, float]:
    """Derives (ulpin, metadata, survey_no, lat, lng, area_m2) for a cell."""
    ring = _ring_of(cell)
    ulpin, meta = parcel_ulpin_from_vertices(ring)
    lat, lng = _centroid_latlng(cell)
    area = _metric_area_m2(cell)
    return (
        ulpin,
        meta,
        _survey_number(idx, int(area) % 7 if area else 0),
        lat,
        lng,
        area,
    )


def synthesize_parcels_for_boundary(
    db: Session,
    boundary_code: str,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """Deterministically synthesises parcels inside one boundary and persists them.

    Works for VILLAGE and TALUKA boundaries (and falls back to the nearest
    village/TALUKA boundary when given a larger jurisdiction). Parcels are
    upserted by derived ULPIN, so re-runs are idempotent.

    :returns: summary dict with counts and sample ULPINs
    """
    b = db.execute(select(AdminBoundary).where(AdminBoundary.code == boundary_code)).scalar_one_or_none()
    if b is None:
        return {"error": f"boundary '{boundary_code}' not found", "synthesized": 0}
    if b.geom is None:
        return {"error": f"boundary '{boundary_code}' has no geometry", "synthesized": 0}

    target_geom = _shapely_of(b)

    # target: smallest available geometry (if taller passed, drill to a child village/taluka)
    target = b
    if b.level == "DISTRICT":
        child = db.execute(
            select(AdminBoundary)
            .where(AdminBoundary.parent_code == b.code, AdminBoundary.level.in_(SYNTH_LEVELS))
            .limit(1)
        ).scalar_one_or_none()
        target = child or b
    elif b.level == "STATE":
        child = db.execute(
            select(AdminBoundary)
            .where(AdminBoundary.parent_code == b.code, AdminBoundary.level.in_(SYNTH_LEVELS))
            .limit(1)
        ).scalar_one_or_none()
        target = child or b

    if target != b:
        target_geom = _shapely_of(target)

    epsg = _utm_epsg(target_geom.bounds[0] + (target_geom.bounds[2] - target_geom.bounds[0]) / 2)
    dims = int(math.sqrt(MAX_PARCELS_PER_VILLAGE))
    cells = _grid_split(target_geom, dims, dims, epsg)[:MAX_PARCELS_PER_VILLAGE]

    existing_ulpins = set(db.execute(
        select(NationalParcel.ulpin).where(NationalParcel.boundary_code == target.code)
    ).scalars().all())

    inserted = 0
    updated = 0
    for idx, cell in enumerate(cells):
        try:
            clipped = _coerce_polygon(cell)
            ulpin, meta, survey_no, lat, lng, area = _derive_for_cell(clipped, idx)
            cell_wkt = clipped.wkt
        except Exception as exc:  # noqa: BLE001
            log.warning("skipped parcel %s/%s: %s", target.code, idx, exc)
            continue
        row = db.execute(select(NationalParcel).where(NationalParcel.ulpin == ulpin)).scalar_one_or_none()
        if row is None:
            row = NationalParcel(ulpin=ulpin)
            db.add(row)
            inserted += 1
        else:
            updated += 1
        row.survey_number = survey_no
        row.boundary_code = target.code
        row.state_code = target.state_code or ""
        row.district_code = target.district_code or ""
        row.geom = f"SRID=4326;{cell_wkt}"
        row.centroid_lat = lat
        row.centroid_lng = lng
        row.area_m2 = area
        row.derivation = meta
        row.zonal_class = _zonal_class(clipped, idx)

    db.commit()
    return {
        "boundary_code": target.code,
        "boundary_name": target.name,
        "boundary_level": target.level,
        "synthesized_new": inserted,
        "recomputed_existing": updated,
        "total_cells": len(cells),
        "sample_ulpin": existing_ulpins.pop() if (force and existing_ulpins) else None,
    }


def ensure_parcels_for_village(db: Session, boundary_code: str) -> Dict[str, Any]:
    """Idempotent wrapper: synthesises parcels only if the village has none yet."""
    n = int(db.execute(
        select(text("COUNT(*)")).select_from(NationalParcel)
        .where(NationalParcel.boundary_code == boundary_code)
    ).scalar())
    if n > 0:
        return {"boundary_code": boundary_code, "already_present": n}
    return synthesize_parcels_for_boundary(db, boundary_code)


def list_synthesized_parcels(
    db: Session,
    boundary_code: str,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Returns synthesized parcels (with derived ULPINs) within one boundary."""
    rows = db.execute(
        select(NationalParcel)
        .where(NationalParcel.boundary_code == boundary_code)
        .order_by(NationalParcel.survey_number)
        .limit(limit)
    ).scalars().all()
    return [
        {
            "ulpin": r.ulpin,
            "survey_number": r.survey_number,
            "boundary_code": r.boundary_code,
            "state_code": r.state_code,
            "centroid_lat": r.centroid_lat,
            "centroid_lng": r.centroid_lng,
            "area_m2": r.area_m2,
            "zonal_class": r.zonal_class,
            "derivation": {
                "cell_key": (r.derivation or {}).get("cell_key"),
                "method": (r.derivation or {}).get("method"),
                "vertex_count": (r.derivation or {}).get("vertex_count"),
                "centroid_latlon": (r.derivation or {}).get("centroid_latlon"),
            },
        }
        for r in rows
    ]


def national_longitude_offset(state_code: str, idx: int) -> int:
    """Deterministic per-state survey offset so survey numbers differ across states."""
    return (sum(ord(c) for c in state_code) + idx * 31) % 999999