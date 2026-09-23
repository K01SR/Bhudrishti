"""Underground asset layer for any selected area.

Vertical cadastre is not only about what is above ground: the volumetric model
has to show what shares the same soil, so pipelines, cables, culverts and
manholes are fetched for whatever area the user is looking at, exactly like the
building footprints.

Coverage is honest about its origin. OpenStreetMap is the only open source for
buried assets and it is very unevenly mapped — dense in some cities, empty
almost everywhere else. This module therefore returns what is genuinely mapped
and reports how much, rather than drawing a plausible-looking network where the
real record does not exist. A missing network is a data gap, not an invitation
to invent pipes.

Depths are not published for most assets. Where a source carries ``depth`` or
``location`` tags those are used and flagged; otherwise the geometry is returned
without a depth and the caller decides how to present it.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.opendata.overpass import (
    AREA_FETCH_BUDGET_S,
    _run_query,
    geometry_touches_radius,
    haversine_m,
)

# Tags that identify a buried or surface asset worth putting in a 3D twin.
_ASSET_FILTERS = (
    'way["man_made"="pipeline"]',
    'way["man_made"="culvert"]',
    'way["man_made"="manhole"]',
    'way["man_made"="drain"]',
    'way["man_made"="sewer"]',
    'relation["man_made"="pipeline"]',
    'way["utility"]',
    'way["power"="line"]',
    'way["telecom"="line"]',
)

# Some mirrors stall on a multi-key union over a wide box, so the query is
# issued in narrow slices and the budget is shared.
_SLICE_DEG = 0.01

_UTILITY_BUDGET_S = 25.0


def _depth_of(tags: Dict[str, str]) -> Tuple[Optional[float], str]:
    """Depth in metres below ground, and how it was obtained."""
    for key in ("depth", "depth:below_ground"):
        if key in tags:
            try:
                return abs(float(str(tags[key]).split()[0])), "source_tag"
            except (ValueError, IndexError):
                pass
    if tags.get("location") == "underground":
        # Tagged underground but unmeasured: depth is not known.
        return None, "tagged_underground_depth_unknown"
    if tags.get("layer") and tags["layer"].lstrip("-").isdigit():
        return abs(float(tags["layer"])) * 2.5, "layer_scaled"
    return None, "unknown"


def _classify(tags: Dict[str, str]) -> str:
    man_made = tags.get("man_made", "")
    utility = tags.get("utility", "")
    if man_made in ("pipeline", "culvert", "drain", "sewer"):
        return f"pipeline:{man_made}"
    if man_made == "manhole":
        return "manhole"
    if utility in ("water", "sewerage", "drainage", "gas", "electricity", "telecom", "heat"):
        return f"utility:{utility}"
    if tags.get("power") == "line":
        return "power:line"
    if tags.get("telecom") == "line":
        return "telecom:line"
    if man_made == "pipeline":
        return "pipeline"
    return "utility:other"


def _parse_geometry(element: Dict[str, Any]) -> List[List[float]]:
    geometry = element.get("geometry")
    if isinstance(geometry, list) and geometry:
        return [[p["lon"], p["lat"]] for p in geometry if p and "lon" in p and "lat" in p]
    nodes = element.get("nodes")
    if isinstance(nodes, list) and nodes:
        return [[n["lon"], n["lat"]] for n in nodes if n and "lon" in n and "lat" in n]
    if element.get("type") == "Node" and "lon" in element and "lat" in element:
        return [[element["lon"], element["lat"]]]
    return []


def _clip_to_area(geometry, lat: float, lon: float, radius_m: float):
    """Drop vertices outside the requested radius, keeping the run that intersects.

    A mapped pipeline is one long way: Overpass returns its whole geometry, so a
    main crossing the area can carry vertices several kilometres away. Those are
    correct data but wrong for a view framed on one area, and they drag the
    rendered line off screen. The contiguous run containing an in-range vertex is
    kept, so the asset still shows where it actually runs through the area.

    Returns ``(geometry, was_clipped)``.
    """
    if len(geometry) < 2:
        return geometry, False
    inside = [haversine_m(lat, lon, float(p[1]), float(p[0])) <= radius_m for p in geometry]
    if all(inside):
        return geometry, False
    if not any(inside):
        return [], False

    # Longest contiguous run of in-range vertices, extending one step either side
    # so the line still meets the edge of the area rather than stopping short.
    best_start, best_len = None, 0
    run_start, run_len = None, 0
    for idx, flag in enumerate(inside + [False]):
        if flag:
            if run_len == 0:
                run_start = idx
            run_len += 1
        elif run_len > 0:
            if run_len > best_len:
                best_start, best_len = run_start, run_len
            run_len = 0
    start = max(0, (best_start or 0) - 1)
    end = min(len(geometry), (best_start or 0) + best_len + 1)
    return geometry[start:end], True


def fetch_underground_assets(
    lat: float,
    lon: float,
    radius: int = 500,
    deadline: Optional[float] = None,
) -> Dict[str, Any]:
    """Return mapped buried assets for an area, with honest coverage reporting.

    An empty ``assets`` list is a valid, meaningful answer: it means nothing is
    mapped there. The payload says so explicitly so the UI can distinguish
    "no data" from "no utilities exist".
    """
    started = time.monotonic()
    budget_end = started + _UTILITY_BUDGET_S
    if deadline is not None:
        budget_end = min(budget_end, deadline)

    half = max(0.0015, min(0.05, radius / 110540.0))
    slices: List[Tuple[float, float, float, float]] = []
    lat_edges = _edges(lat, half)
    lon_edges = _edges(lon, half * max(math.cos(math.radians(lat)), 1e-3))
    for lat0, lat1 in lat_edges:
        for lon0, lon1 in lon_edges:
            slices.append((lat0, lon0, lat1, lon1))

    assets: List[Dict[str, Any]] = []
    seen: set = set()
    errors: List[str] = []
    attempted = 0
    clipped = 0

    for lat0, lon0, lat1, lon1 in slices:
        if time.monotonic() >= budget_end - 1.0:
            break
        bbox = f"{lat0},{lon0},{lat1},{lon1}"
        query = "[out:json][timeout:25];(" + "".join(f + f"({bbox});" for f in _ASSET_FILTERS) + ");out geom;"
        attempted += 1
        try:
            data = _run_query(query, timeout=12.0, attempts=1, deadline=budget_end)
        except Exception as exc:  # noqa: BLE001 - partial coverage is reported, not hidden
            errors.append(str(exc)[:120])
            continue

        for element in data.get("elements", []):
            tags = element.get("tags") or {}
            geometry = _parse_geometry(element)
            if len(geometry) < 1:
                continue
            # Re-check the slice client-side: a mirror has been observed
            # answering a bbox query with elements from elsewhere entirely, and
            # an asset placed under the wrong building is worse than a gap.
            if not geometry_touches_radius(geometry, lat, lon, radius):
                continue
            geometry, was_clipped = _clip_to_area(geometry, lat, lon, radius)
            if not geometry:
                continue
            if was_clipped:
                clipped += 1
            ident = (element.get("type"), element.get("id"))
            if ident in seen:
                continue
            seen.add(ident)
            depth, depth_basis = _depth_of(tags)
            assets.append(
                {
                    "osm_id": f"{element.get('type', 'node')}/{element.get('id')}",
                    "asset_type": _classify(tags),
                    "geometry": geometry,
                    "clipped_to_area": was_clipped,
                    "kind": "line" if len(geometry) > 1 else "point",
                    "name": tags.get("name") or tags.get("ref"),
                    "depth_m": depth,
                    "depth_basis": depth_basis,
                    "surface": tags.get("location") == "ground" or tags.get("man_made") == "manhole",
                    "tags": {k: v for k, v in tags.items() if k in ("material", "diameter", "depth", "operator", "substance", "location", "layer")},
                }
            )

    dtypes: Dict[str, int] = {}
    for a in assets:
        dtypes[a["asset_type"]] = dtypes.get(a["asset_type"], 0) + 1

    return {
        "assets": assets,
        "counts": {
            "assets": len(assets),
            "with_source_depth": sum(1 for a in assets if a["depth_m"] is not None),
            "slices_queried": attempted,
            "slices_planned": len(slices),
            "clipped_to_area": clipped,
        },
        "by_type": dtypes,
        "coverage": {
            # Nothing mapped is the normal case away from a few well-surveyed
            # cities. Say so rather than returning a plausible fake network.
            "mapped": len(assets) > 0,
            "note": (
                f"{len(assets)} asset(s) mapped by OpenStreetMap in this area"
                if assets
                else "No buried assets are mapped in OpenStreetMap for this area. "
                "Underground utility geometry is not published as open data for India, "
                "so an empty layer here means unmapped, not non-existent."
            ),
            "depths_published": sum(1 for a in assets if a["depth_m"] is not None),
        },
        "provenance": {
            "provider": "openstreetmap",
            "dataset": "OpenStreetMap underground assets (man_made=pipeline, manhole, culvert, utility=*)",
            "license": "Open Database License (ODbL) 1.0 - © OpenStreetMap contributors",
            "source_url": f"https://www.openstreetmap.org/#map=17/{lat}/{lon}",
            "authoritative": False,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        },
        "partial": bool(errors) or attempted < len(slices),
        "errors": errors[:3],
    }


def _edges(centre: float, half: float) -> List[Tuple[float, float]]:
    if half <= _SLICE_DEG:
        return [(centre - half, centre + half)]
    edges = []
    span = half * 2
    steps = max(1, int(math.ceil(span / _SLICE_DEG)))
    for i in range(steps):
        lo = centre - half + span * i / steps
        edges.append((lo, lo + span / steps))
    return edges
