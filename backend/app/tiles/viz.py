"""
National thematic visualization layers (Phase 5).

Serves choropleth-ready aggregates computed on-demand from PostGIS over the
real national data so the client can color/filter tiles by:

  * ``fsi``    - FSI value + NBC compliance bucket of persisted twins, per admin unit
  * ``density``- ULPIN parcel density (parcels / km^2) per admin unit
  * ``status`` - twin coverage / verification status share per admin unit
  * ``ulpin-zone`` - dominant zonal class (AGRI / RESIDENTIAL) share

Each returns a GeoJSON FeatureCollection of the unit geometries with calculated
attributes, so a map layer can be styled purely from ``properties.fill``/bucket.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.demo_gate import demo_mode_enabled

router = APIRouter(prefix="/viz", tags=["National Thematic Layers"])

FSI_BUCKETS = {
    "UNDER_0_5": "#1f7a3d",
    "0_5_TO_1_0": "#7bb661",
    "1_0_TO_1_5": "#e0d33c",
    "1_5_TO_2_5": "#f0a202",
    "2_5_TO_4_0": "#e2593c",
    "EXCEEDED": "#9d174d",
    "NO_TWIN": "#e5e7eb",
}

VERIFY_BUCKETS = {
    "VERIFIED": "#16a34a",
    "PENDING": "#f59e0b",
    "NONE": "#e5e7eb",
    "CONFLICT": "#dc2626",
}


def _fsi_bucket(fsi: Optional[float]) -> str:
    if fsi is None:
        return "NO_TWIN"
    if fsi >= 4.0:
        return "EXCEEDED"
    if fsi >= 2.5:
        return "2_5_TO_4_0"
    if fsi >= 1.5:
        return "1_5_TO_2_5"
    if fsi >= 1.0:
        return "1_0_TO_1_5"
    if fsi >= 0.5:
        return "0_5_TO_1_0"
    return "UNDER_0_5"


async def _fetch(
    sql: str,
    params: Optional[Dict[str, Any]] = None,
) -> List[Any]:
    async with AsyncSessionLocal() as db:
        res = await db.execute(text(sql), params or {})
        return res.fetchall()


def _level_table_selection(level: str) -> str:
    allowed = {"STATE": "STATE", "DISTRICT": "DISTRICT", "TALUKA": "TALUKA", "VILLAGE": "VILLAGE"}
    if level not in allowed:
        raise HTTPException(status_code=400, detail="level must be one of STATE/DISTRICT/TALUKA/VILLAGE")
    return allowed[level]


def _unit_scope_sql(lvl: str, jurisdiction_code: Optional[str]) -> tuple[str, Dict[str, Any]]:
    """WHERE fragment + params selecting units of ``lvl``, opt. scoped to a subtree."""
    scope = ""
    params: Dict[str, Any] = {}
    if isinstance(jurisdiction_code, str) and jurisdiction_code:
        scope = "AND (u.code = :jc OR u.parent_code = :jc)"
        params["jc"] = jurisdiction_code
    return scope, params


def _unit_rows_sql(lvl: str, extra_cols: str = "", scope: str = "") -> str:
    select = "ST_AsGeoJSON(u.geom) AS geom_json"
    if extra_cols:
        select += f", {extra_cols}"
    return f"""
    SELECT u.code, u.name, u.level, {select}
    FROM admin_boundaries u
    WHERE u.level = :lvl {scope}
    """


async def _load_admin_tree() -> Dict[str, Dict[str, Any]]:
    """code -> {parent_code, level, children:[...]} for the whole admin tree."""
    rows = await _fetch(
        "SELECT code, parent_code, level FROM admin_boundaries"
    )
    tree: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        code = r._mapping["code"]
        tree[code] = {
            "parent": r._mapping["parent_code"],
            "level": r._mapping["level"],
            "children": [],
        }
    for code, node in tree.items():
        p = node["parent"]
        if p and p in tree:
            tree[p]["children"].append(code)
    return tree


def _rollup_stats(
    tree: Dict[str, Dict[str, Any]],
    leaf: Dict[str, Dict[str, float]],
) -> Dict[str, Dict[str, float]]:
    """Aggregate per-boundary stats up the admin hierarchy (leaf -> root)."""
    totals: Dict[str, Dict[str, float]] = {}
    depth: Dict[str, int] = {}

    def _depth(code: str) -> int:
        if code not in depth:
            parent = tree.get(code, {}).get("parent")
            depth[code] = 0 if not parent or parent not in tree else _depth(parent) + 1
        return depth[code]

    order = sorted(set(leaf.keys()) | set(tree.keys()), key=_depth, reverse=True)
    for code in order:
        node = tree.get(code)
        if node is None:
            totals[code] = dict(leaf[code])
            continue
        acc: Dict[str, float] = dict(leaf.get(code, {}))
        for child in node["children"]:
            ctotal = totals.get(child)
            if not ctotal:
                continue
            for k, v in ctotal.items():
                acc[k] = acc.get(k, 0.0) + v
        totals[code] = acc
    return totals


def _geom(m: Any) -> Optional[Dict[str, Any]]:
    import json

    raw = m["geom_json"]
    return json.loads(raw) if raw else None


@router.get("/fsi/{level}")
async def fsi_layer(level: str, jurisdiction_code: Optional[str] = Query(None)):
    """
    Choropleth of average twin FSI per admin unit, colored by NBC bucket.
    Aggregates twins up the admin hierarchy from their village boundary_code,
    so STATE / DISTRICT / TALUKA / VILLAGE all reflect the whole-India twin data.
    Optionally restrict to descendants of ``jurisdiction_code``.
    """
    lvl = _level_table_selection(level)
    scope, params = _unit_scope_sql(lvl, jurisdiction_code)
    params["lvl"] = lvl

    unit_rows = await _fetch(_unit_rows_sql(lvl, scope=scope), params)

    # national_twins is synthetic (synthetic grid under random.seed(42); the
    # parcels it came from have been purged). Aggregating it here would put
    # fabricated building counts and FSI sums inside an otherwise genuine
    # administrative rollup, so the leaf stats stay empty unless the flag is on.
    if demo_mode_enabled():
        leaf_rows = await _fetch(
            "SELECT t.boundary_code AS code, COUNT(*) AS twins, "
            "COALESCE(SUM(t.fsi), 0) AS fsi_sum, "
            "COUNT(*) FILTER (WHERE t.fsi_status='EXCEEDED') AS exceeded "
            "FROM national_twins t GROUP BY t.boundary_code"
        )
    else:
        leaf_rows = []
    leaf: Dict[str, Dict[str, float]] = {}
    for r in leaf_rows:
        m = r._mapping
        if m["code"]:
            leaf[m["code"]] = {"twins": m["twins"], "fsi_sum": m["fsi_sum"], "exceeded": m["exceeded"]}

    totals = _rollup_stats(await _load_admin_tree(), leaf)

    features = []
    for r in unit_rows:
        m = r._mapping
        stats = totals.get(m["code"], {})
        twins = int(stats.get("twins", 0))
        avg = (stats.get("fsi_sum", 0.0) / twins) if twins else None
        props = {
            "name": m["name"],
            "code": m["code"],
            "level": m["level"],
            "avg_fsi": round(avg, 2) if avg is not None else None,
            "twins": twins,
            "exceeded": int(stats.get("exceeded", 0)),
            "fsi_bucket": _fsi_bucket(avg),
            "fill": FSI_BUCKETS[_fsi_bucket(avg)],
        }
        features.append({"type": "Feature", "geometry": _geom(m), "properties": props})
    return {"type": "FeatureCollection", "features": features}


@router.get("/density/{level}")
async def density_layer(level: str, jurisdiction_code: Optional[str] = Query(None)):
    """
    ULPIN parcel density (parcels / km^2) per admin unit + zone share,
    aggregated up the admin hierarchy like the other layers.
    """
    lvl = _level_table_selection(level)
    scope, params = _unit_scope_sql(lvl, jurisdiction_code)
    params["lvl"] = lvl

    unit_rows = await _fetch(_unit_rows_sql(
        lvl,
        "ROUND((ST_Area(u.geom::geography) / 1000000.0)::numeric, 3) AS area_km2",
        scope=scope,
    ), params)

    # Purged, so this is empty in a default deployment; gated for consistency
    # with the other synthetic aggregates.
    if demo_mode_enabled():
        leaf_rows = await _fetch(
            "SELECT p.boundary_code AS code, COUNT(*) AS parcels, "
            "COUNT(*) FILTER (WHERE p.zonal_class='AGRI') AS agri "
            "FROM national_parcels p GROUP BY p.boundary_code"
        )
    else:
        leaf_rows = []
    leaf: Dict[str, Dict[str, float]] = {}
    for r in leaf_rows:
        m = r._mapping
        if m["code"]:
            leaf[m["code"]] = {"parcels": m["parcels"], "agri": m["agri"]}

    totals = _rollup_stats(await _load_admin_tree(), leaf)

    features = []
    for r in unit_rows:
        m = r._mapping
        stats = totals.get(m["code"], {})
        parcels = int(stats.get("parcels", 0))
        area = m["area_km2"] or 0
        density = round(parcels / max(area, 1e-6), 2)
        agri = int(stats.get("agri", 0))
        res_share = round((parcels - agri) / max(parcels, 1), 3)
        props = {
            "name": m["name"],
            "code": m["code"],
            "level": m["level"],
            "parcels": parcels,
            "area_km2": area,
            "agri": agri,
            "density_per_km2": density,
            "residential_share": res_share,
            "fill": _density_color(density),
        }
        features.append({"type": "Feature", "geometry": _geom(m), "properties": props})
    return {"type": "FeatureCollection", "features": features}


def _density_color(d: float) -> str:
    if d >= 100:
        return "#581c87"
    if d >= 25:
        return "#6d28d9"
    if d >= 5:
        return "#8b5cf6"
    if d >= 1:
        return "#c4b5fd"
    return "#f3f4f6"


@router.get("/status/{level}")
async def coverage_layer(level: str, jurisdiction_code: Optional[str] = Query(None)):
    """
    Twin coverage / build status per admin unit (what fraction of parcels
    have a persisted 3D twin), aggregated up the admin hierarchy.
    """
    lvl = _level_table_selection(level)
    scope, params = _unit_scope_sql(lvl, jurisdiction_code)
    params["lvl"] = lvl

    unit_rows = await _fetch(_unit_rows_sql(lvl, scope=scope), params)

    # Same reasoning as the leaf stats above: both tables are synthetic and
    # national_parcels is now empty. Keep the keys present so the response
    # shape is stable, but report zeroes rather than fabricated counts.
    if demo_mode_enabled():
        parcel_rows = await _fetch(
            "SELECT p.boundary_code AS code, COUNT(*) AS parcels "
            "FROM national_parcels p GROUP BY p.boundary_code"
        )
        twin_rows = await _fetch(
            "SELECT t.boundary_code AS code, COUNT(*) AS twinned "
            "FROM national_twins t GROUP BY t.boundary_code"
        )
    else:
        parcel_rows = []
        twin_rows = []
    tree = await _load_admin_tree()

    def _to_leaf(rows: List[Any], key: str) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for r in rows:
            m = r._mapping
            if m["code"]:
                out[m["code"]] = {key: m[key]}
        return out

    tot_p = _rollup_stats(tree, _to_leaf(parcel_rows, "parcels"))
    tot_t = _rollup_stats(tree, _to_leaf(twin_rows, "twinned"))

    features = []
    for r in unit_rows:
        m = r._mapping
        parcels = int(tot_p.get(m["code"], {}).get("parcels", 0))
        twinned = int(tot_t.get(m["code"], {}).get("twinned", 0))
        cov = round(100.0 * twinned / parcels, 1) if parcels else 0.0
        status = "VERIFIED" if cov >= 90 else ("PENDING" if cov > 0 else "NONE")
        props = {
            "name": m["name"],
            "code": m["code"],
            "level": m["level"],
            "parcels": parcels,
            "twinned": twinned,
            "coverage_pct": cov,
            "status": status,
            "fill": VERIFY_BUCKETS[status],
        }
        features.append({"type": "Feature", "geometry": _geom(m), "properties": props})
    return {"type": "FeatureCollection", "features": features}


@router.get("/layers")
async def list_layers():
    """Enumeration of available thematic layers and buckets (for UI dropdowns)."""
    return {
        "fsi": {
            "path": "/viz/fsi/{level}",
            "description": "Average twin FSI per admin unit (NBC bucket)",
            "buckets": {k: v for k, v in FSI_BUCKETS.items()},
        },
        "density": {
            "path": "/viz/density/{level}",
            "description": "ULPIN parcel density per km^2 + residential share",
            "fill_scale": "qualitative purple ramp",
        },
        "status": {
            "path": "/viz/status/{level}",
            "description": "Twin coverage / verification status per admin unit",
            "buckets": {k: v for k, v in VERIFY_BUCKETS.items()},
        },
    }