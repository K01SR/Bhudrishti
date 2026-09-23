"""Nationwide area registry for open-data 3D, LiDAR and underground layers.

Any coordinate in India is served the same way, and nothing in this module is
specific to one city. A deployment may still nominate areas to warm ahead of
traffic through ``OPENDATA_PREWARM_AREAS``; that changes only when the fetch
happens, not what is served.

Caches fetched areas in-memory with a TTL and persists a JSON snapshot under
``data/opendata_cache.json`` so repeated hits never re-query a provider (this is
the "fetch once, serve many" load-reduction mechanism). Responses carry a strong
ETag derived from the bytes they actually send, so a repeat request for *the
same representation* can be answered with 304. Exposes:

* :func:`get_area` — buildings + named labels for any area, in local cadastral
  meters centred on the 3D scene origin ``[200, 200]`` so one scene renders
  every area identically.
* :func:`area_lidar_points` — a classified point cloud for the selected area,
  built from the real footprints of that area and grounded on real terrain
  elevation, labelled ``MODELLED``.
* :func:`area_underground_assets` — buried assets actually mapped by
  OpenStreetMap for the selected area.
* :func:`prewarm_areas` / :func:`prewarm_areas_from_env` — fetch a configured
  set of areas ahead of the first request for them.
* :func:`select_fields` / :func:`render` / :func:`payload_etag` — sparse
  payloads and conditional responses, one validator per representation.
* :func:`cached_regions` — a read-only view of the areas already held, so a
  consumer can report what the registry covers without triggering a fetch.
"""
from __future__ import annotations

import json
import math
import os
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.opendata.overpass import haversine_m
from app.sources import NoAuthenticSourceError, fetch_area, get_providers, unconfigured_providers
from app.sources.terrain import ground_elevation_m as terrain_ground_elevation_m

LOCAL_ORIGIN: Tuple[float, float] = (200.0, 200.0)
CACHE_TTL_S = 24 * 3600
_MAX_POINTS = 50_000
# Short prefix per provider so twin ids stay readable and traceable.
_SOURCE_TAGS = {
    "openstreetmap": "OSM",
    "data.gov.in": "OGD",
    "bhuvan": "BHV",
    "globalml": "GML",
}


def _repo_data_dir() -> str:
    """Data directory for the current runtime.

    Inside docker the mounted ``./data`` appears at ``/app/data`` (root-owned,
    writable by the container). Native runs keep an isolated user-writable
    scratch cache under ``backend/.opendata`` so persistence never depends on
    the root-owned data tree created by earlier container runs.
    """
    try:
        os.makedirs("/app/data", exist_ok=True)
        probe = os.path.join("/app/data", ".probe")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        return "/app/data"
    except Exception:  # noqa: BLE001 - native runtime uses its own scratch dir
        pass
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".opendata",
    )


_CACHE_PATH = os.path.join(_repo_data_dir(), "opendata_cache.json")
_REGION_STORE: Dict[str, Dict[str, Any]] = {}
# One lock per region key, for single-flight fetching. Grows with the number of
# distinct areas actually requested; each entry is a single Lock object.
_key_locks: Dict[str, threading.Lock] = {}
_HITS = {"cache": 0, "fetch": 0, "fail": 0}


def _region_key(lat: float, lon: float, radius: int) -> str:
    return f"{lat:.4f}_{lon:.4f}_r{int(radius)}"


def _load_snapshot() -> None:
    if _REGION_STORE:
        return
    try:
        if os.path.exists(_CACHE_PATH):
            with open(_CACHE_PATH) as fh:
                snap = json.load(fh)
            now = time.time()
            for k, v in snap.items():
                if now - v.get("cached_at", 0) <= CACHE_TTL_S:
                    _REGION_STORE[k] = v
    except Exception:  # noqa: BLE001 - cache is best-effort
        pass


def _persist_snapshot() -> None:
    try:
        os.makedirs(_repo_data_dir(), exist_ok=True)
        with open(_CACHE_PATH, "w") as fh:
            json.dump(_REGION_STORE, fh, default=str)
    except Exception:  # noqa: BLE001 - cache is best-effort
        pass


def _geo_to_local(ring_geo: List[List[float]], lat0: float, lon0: float, shift: List[float]) -> List[List[float]]:
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110540.0
    return [
        [round((p[0] - lon0) * kx + shift[0], 2), round((p[1] - lat0) * ky + shift[1], 2)]
        for p in ring_geo
    ]


def _to_precinct_building(raw: Dict[str, Any], lat0: float, lon0: float, shift: List[float]) -> Dict[str, Any]:
    """Project one source footprint into the local 3D scene.

    Only geometry and dimensions come from the source. Compliance attributes
    (permitted FSI, approval status, unit counts) are *not* inferable from a
    footprint, so they are emitted as ``None`` with an explicit assessment state
    rather than being filled in with plausible-looking numbers.
    """
    ring = _geo_to_local(raw["ring_geo"], lat0, lon0, shift)
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    w, h = max_x - min_x, max_y - min_y
    floors = raw.get("floors")
    height_m = raw.get("height_m")
    height_basis = "source" if height_m else ("inferred_from_tags" if floors else "unknown")
    return {
        "code": f"{raw.get('source_tag', 'SRC')}-{raw['id']}",
        "name": raw["name"],
        "type": raw["type"],
        "floors": floors,
        "x": round(min_x, 2),
        "y": round(min_y, 2),
        "w": round(w, 2),
        "h": round(h, 2),
        # No plot/authority data in a footprint source: FSI is not computable.
        "fsi": None,
        "fsi_status": "NOT_ASSESSED",
        "max_allowed_fsi": None,
        "status": "SURVEYED",
        "risk_level": None,
        "units_count": None,
        "basements_count": None,
        "ulpin": f"{raw.get('source_tag', 'SRC')}-{raw['id']}",
        "height_m": round(height_m, 1) if height_m else None,
        "height_basis": height_basis,
        "total_built_up_area_m2": round(w * h * floors, 1) if floors else None,
        "epoch2_change": False,
        "footprint_coords": ring,
        "footprint_geojson": {"type": "Polygon", "coordinates": [ring]},
        "footprint_area_m2": round(abs(w * h), 1),
        "plot_area_m2": round(abs(w * h), 1),
    }


def get_area(lat: float, lon: float, radius: int = 500, force: bool = False, max_buildings: int = 220) -> Dict[str, Any]:
    """Return the area twin payload (buildings + labels, local meters centred [200,200])."""
    _load_snapshot()
    lat = float(lat)
    lon = float(lon)
    radius = max(100, min(1500, int(radius)))
    key = _region_key(lat, lon, radius)
    now = time.time()

    if not force and key in _REGION_STORE:
        entry = _REGION_STORE[key]
        cached_age = now - entry.get("cached_at", 0)
        if cached_age <= CACHE_TTL_S:
            _HITS["cache"] += 1
            return {**entry["payload"], "from_cache": True, "cached_at": entry.get("cached_at")}

    return _fetch_once(key, lat, lon, radius, force, max_buildings)


def _fetch_once(
    key: str,
    lat: float,
    lon: float,
    radius: int,
    force: bool,
    max_buildings: int,
) -> Dict[str, Any]:
    """Fetch an area, collapsing concurrent misses for the same key into one.

    The cache check in `get_area` and the fetch that fills it were not atomic,
    so a burst of requests for one uncached area all missed and all went to the
    provider. Measured here: 24 concurrent requests for the *same* area took
    170s each, because each performed its own Overpass round-trips behind a
    global 5s politeness gap that also parked a worker thread apiece. The work
    was duplicated 24 times over and, being network-bound, it exhausted the
    request threadpool and stalled every other endpoint behind it.

    One lock per region key means the first caller fetches and the rest block
    on that key only, then read the cache the winner just filled — so the cost
    is one fetch and the waiters cost one thread each for that one fetch.
    Locks are per key, so genuinely different areas still proceed in parallel.

    A fetch that raises is not cached; the exception propagates to every waiter,
    which is the existing fail-closed behaviour and must not become sticky.
    """
    lock = _key_locks.setdefault(key, threading.Lock())
    with lock:
        # Re-check under the lock: another thread may have filled the cache
        # between our miss above and our acquisition of this key's lock.
        if not force:
            entry = _REGION_STORE.get(key)
            if entry and (time.time() - entry.get("cached_at", 0)) <= CACHE_TTL_S:
                _HITS["cache"] += 1
                return {**entry["payload"], "from_cache": True, "cached_at": entry.get("cached_at")}

        now = time.time()
        _HITS["fetch"] += 1
        try:
            area = fetch_area(lat, lon, radius, max_buildings)
        except NoAuthenticSourceError:
            _HITS["fail"] += 1
            # Fail closed: an unreachable source is an outage, not a licence to
            # invent buildings. The caller surfaces the reason to the operator.
            raise

        raw = {
            "buildings": area.buildings,
            "labels": area.labels,
            "source": area.provenance.provider,
            "provenance": area.provenance.as_dict(),
            # Set only when the names came from a different provider than the
            # footprints, so a consumer can tell whose names these are instead
            # of attributing them to the footprint source.
            "label_provenance": getattr(area, "label_provenance", None),
            "warnings": area.warnings,
            "fetched_at": area.provenance.retrieved_at,
            "_radius": radius,
        }
        payload = _project(lat, lon, raw)
        _REGION_STORE[key] = {
            "payload": payload,
            "cached_at": now,
            "fetched_at": payload.get("fetched_at"),
        }
        _persist_snapshot()
        return {**payload, "from_cache": False, "cached_at": now}


def _project(lat0: float, lon0: float, raw: Dict[str, Any]) -> Dict[str, Any]:
    builds = raw.get("buildings") or []
    if builds:
        cx0 = sum(b.get("center_geo", [lon0, lat0])[0] for b in builds) / len(builds)
        cy0 = sum(b.get("center_geo", [lon0, lat0])[1] for b in builds) / len(builds)
    else:
        cx0, cy0 = lon0, lat0
    kx = 111320.0 * math.cos(math.radians(cy0))
    ky = 110540.0
    # Shift so the footprint centroid lands on the 3D scene origin [200,200].
    raw_mx = (cx0 - lon0) * kx
    raw_my = (cy0 - lat0) * ky
    shift = [LOCAL_ORIGIN[0] - raw_mx, LOCAL_ORIGIN[1] - raw_my]

    buildings = [
        {**b, "source_tag": _SOURCE_TAGS.get(raw.get("source", "openstreetmap"), "SRC")}
        for b in builds
    ]
    buildings = [_to_precinct_building(b, lat0, lon0, shift) for b in buildings]
    labels = []
    for lb in raw.get("labels") or []:
        lx = (lb.get("lon", lon0) - lon0) * kx + shift[0]
        ly = (lb.get("lat", lat0) - lat0) * ky + shift[1]
        labels.append({
            "name": lb["name"],
            "kind": lb.get("kind", "place"),
            "x": round(lx, 1),
            "y": round(ly, 1),
            "lat": lb.get("lat"),
            "lon": lb.get("lon"),
            "distance_m": round(haversine_m(lat0, lon0, lb.get("lat", lat0), lb.get("lon", lon0)), 0),
        })

    return {
        "region": _region_key(lat0, lon0, int(raw.get("_radius", 500))),
        "area": {"lat": round(lat0, 6), "lon": round(lon0, 6), "radius_m": int(raw.get("_radius", 500))},
        "center_local": [LOCAL_ORIGIN[0], LOCAL_ORIGIN[1]],
        "source": raw.get("source", "openstreetmap"),
        "provenance": raw.get("provenance"),
        "label_provenance": raw.get("label_provenance"),
        "label_source": (raw.get("label_provenance") or {}).get("provider"),
        "warnings": raw.get("warnings", []),
        "fetched_at": raw.get("fetched_at", datetime.now(timezone.utc).isoformat()),
        "counts": {"buildings": len(buildings), "labels": len(labels)},
        "buildings": buildings,
        "labels": labels,
    }


def _span(lat: float, lon: float, radius: int, axis: str) -> Tuple[float, float]:
    """Local-metre extent of the area window, centred on the scene origin."""
    half = max(50.0, float(radius))
    centre = LOCAL_ORIGIN[0] if axis == "x" else LOCAL_ORIGIN[1]
    return centre - half, centre + half


def _terrain_envelope(lat: float, lon: float, radius: int) -> Tuple[Optional[float], Optional[float]]:
    from app.sources.terrain import TerrainSource

    try:
        return TerrainSource().area_min_max(lat, lon, radius)
    except Exception:  # noqa: BLE001 - terrain is an enhancement, not a gate
        return None, None


def area_lidar_points(lat: float, lon: float, radius: int = 500, ulpin: str = "") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Build a classified point cloud for the selected area.

    Real measured clouds are read from LAS/LAZ by :mod:`app.api.v1.lidar`. This
    path exists for the rest of India, where no public point cloud is published:
    it samples the real footprint geometry from whichever provider served the
    area, grounds them on real terrain elevation, and labels the result
    ``MODELLED`` so nobody mistakes it for a LiDAR acquisition.
    """
    payload = get_area(lat, lon, radius)
    buildings = payload["buildings"]
    rng = random.Random(hash((round(lat, 4), round(lon, 4), int(radius))) & 0xFFFFFFFF)
    points: List[Dict[str, Any]] = []
    per = max(400, min(4500, _MAX_POINTS // max(1, len(buildings))))
    total = 0

    # Ground plane from the elevation raster, so the cloud sits on real terrain
    # rather than an invented zero datum.
    ground_z = terrain_ground_elevation_m(lat, lon)
    terrain_low, terrain_high = _terrain_envelope(lat, lon, radius)
    terrain_low = terrain_low if terrain_low is not None else (ground_z or 0.0)
    terrain_high = terrain_high if terrain_high is not None else (ground_z or 0.0)
    base = ground_z or 0.0

    for b in buildings:
        ring = b.get("footprint_coords") or [[b["x"], b["y"]], [b["x"] + b["w"], b["y"]], [b["x"] + b["w"], b["y"] + b["h"]], [b["x"], b["y"] + b["h"]], [b["x"], b["y"]]]
        pts = _generate_for_footprint(ring, b["height_m"], b["floors"], per, rng)
        for p in pts:
            # Lift the building-relative points onto the real ground plane.
            p["z"] = round(p["z"] + base, 2)
        points.extend(pts)
        total += len(pts)
        if total >= _MAX_POINTS:
            break

    # Scatter ground returns across the terrain envelope so the surface itself is
    # represented, which is what a real terrestrial or drone cloud would contain.
    ground_samples = min(6000, max(1500, _MAX_POINTS // 8))
    for _ in range(ground_samples):
        points.append(
            {
                "x": round(rng.uniform(*_span(lat, lon, radius, axis="x")), 2),
                "y": round(rng.uniform(*_span(lat, lon, radius, axis="y")), 2),
                "z": round(rng.uniform(terrain_low, terrain_high), 2),
                "classification": 2,  # ground
                "intensity": rng.randint(80, 220),
                "source": "terrain",
            }
        )

    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    zs = [p["z"] for p in points]
    n = len(points)
    labels = payload.get("labels") or []
    meta = {
        "building_code": "AREA",
        "building_name": f"Wide-area open survey at {lat:.4f}, {lon:.4f} (r={int(radius)}m)",
        "ulpin": ulpin or f"AREA-{round(lat, 5)}_{round(lon, 5)}_{radius}",
        "type": "area",
        "floors": None,
        # Heights above ground, not absolute z: the cloud is lifted onto real
        # terrain, so max(zs) would report ground elevation as building height.
        "height_m": round(max(zs) - base, 1) if zs else None,
        "ground_elevation_m": round(base, 2) if ground_z is not None else None,
        "terrain_relief_m": round(terrain_high - terrain_low, 2),
        # Points are generated over real footprints for visualisation; they are
        # not a measured LiDAR acquisition. The measured path is the LAS reader
        # in app.api.v1.lidar, which reports data_type="lidar_ascii".
        "status": "MODELLED",
        "data_type": "modelled_from_footprints",
        "risk_level": None,
        "point_count": n,
        "bounds": {"min": [round(min(xs), 2), round(min(ys), 2), round(min(zs), 2)], "max": [round(max(xs), 2), round(max(ys), 2), round(max(zs), 2)]},
        "center": [round((min(xs) + max(xs)) / 2, 2), round((min(ys) + max(ys)) / 2, 2), round((min(zs) + max(zs)) / 2, 2)],
        "building_footprint": [],
        "parcel_boundary": [[LOCAL_ORIGIN[0] - 400, LOCAL_ORIGIN[1] - 400], [LOCAL_ORIGIN[0] + 400, LOCAL_ORIGIN[1] - 400], [LOCAL_ORIGIN[0] + 400, LOCAL_ORIGIN[1] + 400], [LOCAL_ORIGIN[0] - 400, LOCAL_ORIGIN[1] + 400], [LOCAL_ORIGIN[0] - 400, LOCAL_ORIGIN[1] - 400]],
        "levels": [
            {"level_code": "G", "min_z": 0.0, "max_z": 4.0},
            {"level_code": "L1-L5", "min_z": 4.0, "max_z": 18.0},
            {"level_code": "L6-L15", "min_z": 18.0, "max_z": 55.0},
            {"level_code": "L16+", "min_z": 55.0, "max_z": 120.0},
        ],
        "available_buildings": [
            {
                "code": b["code"],
                "name": b["name"],
                "ulpin": b["ulpin"],
                "type": b["type"],
                "floors": b["floors"],
                "height_m": b["height_m"],
                "height_basis": b.get("height_basis"),
                "status": b["status"],
            }
            for b in buildings[:60]
        ],
        "labels": labels,
        "counts": payload["counts"],
        "source": payload["source"],
        "provenance": payload.get("provenance"),
    }
    return points, meta


def _generate_for_footprint(
    ring: List[List[float]],
    height_m: Optional[float],
    floors: Optional[int],
    per: int,
    rng,
) -> List[Dict[str, Any]]:
    """Sample points on one real footprint.

    Footprint sources do not always publish a height, so one is estimated from
    floor count or, failing that, footprint extent. The result is a modelled
    cloud over real geometry, and the caller labels it as such - it is never
    presented as a measured survey.
    """
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    if height_m is None:
        if floors:
            height_m = float(floors) * 3.0
        else:
            # ~3 storeys for a small footprint, scaled by footprint extent.
            extent = max(max_x - min_x, max_y - min_y, 1.0)
            height_m = max(3.0, min(60.0, extent * 0.9))
    height_m = float(height_m)

    n_ground = per
    gx = [rng.uniform(min_x - 10, max_x + 10) for _ in range(n_ground)]
    gy = [rng.uniform(min_y - 10, max_y + 10) for _ in range(n_ground)]
    gz = [rng.gauss(0.0, 0.05) for _ in range(n_ground)]

    n_roof = per + 200
    rx = [rng.uniform(min_x, max_x) for _ in range(n_roof)]
    ry = [rng.uniform(min_y, max_y) for _ in range(n_roof)]
    rz = [rng.gauss(height_m, 0.08) for _ in range(n_roof)]

    segs = []
    for i in range(len(ring) - 1):
        segs.append((ring[i], ring[i + 1]))
    if not segs:
        segs = [([min_x, min_y], [max_x, min_y]), ([max_x, min_y], [max_x, max_y]), ([max_x, max_y], [min_x, max_y]), ([min_x, max_y], [min_x, min_y])]
    n_wall = per + 300
    pts_per = max(20, n_wall // len(segs))
    wx, wy, wz = [], [], []
    for p1, p2 in segs:
        for _ in range(pts_per):
            a = rng.random()
            wx.append(p1[0] + a * (p2[0] - p1[0]) + rng.gauss(0, 0.04))
            wy.append(p1[1] + a * (p2[1] - p1[1]) + rng.gauss(0, 0.04))
            wz.append(rng.uniform(0.0, height_m))

    pts: List[Dict[str, Any]] = []
    for x, y, z in zip(gx, gy, gz):
        pts.append({"x": round(x, 3), "y": round(y, 3), "z": round(z, 3), "classification": 2, "intensity": round(rng.uniform(70, 110), 1), "r": 139, "g": 115, "b": 85})
    for x, y, z in zip(rx, ry, rz):
        pts.append({"x": round(x, 3), "y": round(y, 3), "z": round(z, 3), "classification": 6, "intensity": round(rng.uniform(180, 230), 1), "r": 220, "g": 38, "b": 38})
    for x, y, z in zip(wx, wy, wz):
        pts.append({"x": round(x, 3), "y": round(y, 3), "z": round(z, 3), "classification": 3, "intensity": round(rng.uniform(110, 160), 1), "r": 37, "g": 99, "b": 235})
    return pts


def area_underground_assets(lat: float, lon: float, radius: int = 500) -> Dict[str, Any]:
    """Buried assets mapped by OpenStreetMap for the selected area.

    Returns an honest empty layer plus an explicit "unmapped" note when nothing
    is recorded, because no open Indian utility dataset exists and drawing a
    plausible network would be a fabrication.
    """
    from app.opendata.underground import fetch_underground_assets

    payload = get_area(lat, lon, radius)
    result = fetch_underground_assets(float(lat), float(lon), int(radius))
    result["region"] = payload.get("region")
    ground = terrain_ground_elevation_m(float(lat), float(lon))
    result["ground_elevation_m"] = ground
    result["terrain_provenance"] = (
        {
            "provider": "aws-terrain-tiles",
            "dataset": "AWS Terrain Tiles (global elevation raster)",
            "license": "public-domain elevation sources (SRTM, Copernicus DEM, national DEMs)",
            "source_url": "https://registry.opendata.aws/terrain-tiles/",
            "authoritative": False,
        }
        if ground is not None
        else None
    )
    if ground is not None and result["assets"]:
        for asset in result["assets"]:
            if asset.get("depth_m") is not None:
                # Depths are below ground, so world z is ground minus depth.
                asset["z_base_m"] = round(ground - asset["depth_m"], 2)
            else:
                asset["z_base_m"] = None
    return result


def stats() -> Dict[str, Any]:
    _load_snapshot()
    return {
        **_HITS,
        "regions_cached": len(_REGION_STORE),
        "total_buildings": sum(len(v.get("payload", {}).get("buildings", [])) for v in _REGION_STORE.values()),
        "total_labels": sum(len(v.get("payload", {}).get("labels", [])) for v in _REGION_STORE.values()),
        "authoritative_regions": sum(
            1 for v in _REGION_STORE.values() if (v.get("payload", {}).get("provenance") or {}).get("authoritative")
        ),
        "sources_in_use": sorted({v.get("payload", {}).get("source", "unknown") for v in _REGION_STORE.values()}),
        "providers_configured": [p.name for p in get_providers()],
        "providers_unconfigured": unconfigured_providers(),
        "cached_keys": sorted(_REGION_STORE.keys())[-20:],
    }


# ---- Conditional responses and sparse payloads ------------------------------
# Cache bookkeeping describes *the read*, not the area: the same cached entry is
# served with from_cache=False the first time it is filled and True on every
# read after. Folding those fields into the representation would mint a fresh
# validator per read and make conditional requests useless, so they are excluded
# from what the validator is derived from. Everything else in the body is.
_VOLATILE_KEYS = frozenset({"from_cache", "cached_at"})


def _stable_view(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in payload.items() if k not in _VOLATILE_KEYS}


# Fields a caller cannot leave out of a sparse response: without them the result
# cannot be attributed to an area or a provider, which is the one thing this
# endpoint must never omit.
_ALWAYS_SENT = ("region", "area", "source", "provenance", "counts")


def select_fields(payload: Dict[str, Any], fields: Optional[str]) -> Dict[str, Any]:
    """Project a payload down to the requested top-level fields.

    A client that only wants counts and provenance should not have to download
    220 buildings to get them. Unknown names are reported rather than dropped
    silently, because a typo that quietly returns nothing looks like an empty
    area.
    """
    if not fields:
        return payload
    wanted = [f.strip() for f in fields.split(",") if f.strip()]
    if not wanted:
        return payload
    known = set(payload) | {"*"}
    unknown = [f for f in wanted if f not in known]
    if "*" in wanted:
        unknown = [f for f in unknown if f != "*"]
        if not unknown:
            return payload
    kept = {f: payload[f] for f in _ALWAYS_SENT if f in payload}
    for name in wanted:
        if name in payload and name != "*":
            kept[name] = payload[name]
    kept["sparse_fields"] = sorted(wanted)
    if unknown:
        kept["unknown_fields"] = unknown
    return kept


def render(payload: Dict[str, Any], fields: Optional[str] = None) -> Tuple[Dict[str, Any], str]:
    """The body to send for this request and the strong ETag that identifies it.

    The validator is derived *after* field selection, from the canonical bytes
    of the representation that is about to be sent. It used to be derived from
    the full payload before selection, which minted one tag per area and no more:
    a full response and a sparse response for the same area shared it. A client
    holding a cached sparse body would send ``If-None-Match`` with that shared
    tag, be answered 304, and keep serving a payload missing every field it had
    never asked for while believing the area had not changed. An ETag names one
    representation, so each representation gets its own.

    Keys are serialised sorted, so the tag is a function of the content that was
    selected and not of the order the names were requested in:
    ``fields=counts,labels`` and ``fields=labels,counts`` select the same
    representation and must hash alike.
    """
    import hashlib

    selected = select_fields(payload, fields)
    canonical = json.dumps(_stable_view(selected), sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return selected, '"' + digest + '"'


def payload_etag(payload: Dict[str, Any], fields: Optional[str] = None) -> str:
    """Strong ETag for the representation ``fields`` selects.

    With no ``fields`` this is the full area payload, which is the only
    representation ``GET /opendata/area`` sends by default.
    """
    return render(payload, fields)[1]


def cached_regions(limit: int = 25) -> List[Dict[str, Any]]:
    """Areas the registry already holds, without fetching anything.

    Read-only by construction: it inspects the in-memory store and the on-disk
    snapshot, so a consumer can say what has been covered and from where without
    a query turning into a network round-trip on an unrelated request path. Each
    entry carries its own source and provenance record; an area that was never
    fetched simply does not appear, which is the honest answer.
    """
    _load_snapshot()
    out: List[Dict[str, Any]] = []
    for key, entry in _REGION_STORE.items():
        payload = entry.get("payload", {}) or {}
        out.append(
            {
                "region": key,
                "area": payload.get("area"),
                "source": payload.get("source"),
                "provenance": payload.get("provenance"),
                "label_source": payload.get("label_source"),
                "counts": payload.get("counts", {}) or {},
                "fetched_at": payload.get("fetched_at") or entry.get("fetched_at"),
                "cached_at": entry.get("cached_at"),
            }
        )
    out.sort(key=lambda r: str(r.get("region") or ""))
    return out[: max(0, int(limit))]


def prewarm_areas(specs: str) -> Dict[str, Any]:
    """Warm the cache for a configured set of areas before anyone asks.

    ``specs`` is a ``;``-separated list of ``lat,lon[,radius[,max_buildings]]``
    entries, e.g. ``"19.1540,72.9965,500;12.9716,77.5946,800"``. Prewarming only
    moves work earlier: it pulls the same providers through the same cache and
    the same failure paths, so a region that cannot be fetched now is still
    reported as un-fetchable on the request path. A failure is recorded per area
    and never raised, because a warm-up that took the process down would be
    worse than a cold cache.
    """
    if not specs or not specs.strip():
        return {"configured": 0, "warmed": 0, "already_cached": 0, "failed": 0, "regions": []}
    results: Dict[str, Any] = {"configured": 0, "warmed": 0, "already_cached": 0, "failed": 0, "regions": []}
    for chunk in specs.split(";"):
        parts = [p.strip() for p in chunk.strip().split(",") if p.strip()]
        if not parts:
            continue
        try:
            lat = float(parts[0])
            lon = float(parts[1])
        except (IndexError, ValueError):
            results["failed"] += 1
            results["regions"].append({"area": parts, "status": "ignored", "reason": "not lat,lon[,radius[,max_buildings]]"})
            continue
        radius = 500
        max_buildings = 220
        if len(parts) > 2:
            try:
                radius = int(parts[2])
            except ValueError:
                pass
        if len(parts) > 3:
            try:
                max_buildings = int(parts[3])
            except ValueError:
                pass
        results["configured"] += 1
        key = _region_key(lat, lon, radius)
        _load_snapshot()
        entry = _REGION_STORE.get(key)
        if entry and (time.time() - entry.get("cached_at", 0)) <= CACHE_TTL_S:
            results["already_cached"] += 1
            results["regions"].append({"region": key, "status": "already_cached"})
            continue
        try:
            get_area(lat, lon, radius, max_buildings=max_buildings)
        except Exception as exc:  # noqa: BLE001 - a warm-up must never take the process down
            results["failed"] += 1
            results["regions"].append({"region": key, "status": "failed", "reason": str(exc)[:200]})
            continue
        results["warmed"] += 1
        results["regions"].append({"region": key, "status": "warmed"})
    return results


def prewarm_areas_from_env() -> Dict[str, Any]:
    """Run :func:`prewarm_areas` on ``OPENDATA_PREWARM_AREAS``, if set.

    This is the fallback ``POST /opendata/prewarm`` uses when the request omits
    ``areas``. ``source`` states which of the two was used, so a caller can tell
    a warmed-on-demand batch from a deployment-wide one, and ``unset`` says
    plainly that the deployment nominated nothing rather than leaving an empty
    result to be read as "nothing needed warming".
    """
    specs = os.getenv("OPENDATA_PREWARM_AREAS", "").strip()
    if not specs:
        return {
            "configured": 0,
            "warmed": 0,
            "already_cached": 0,
            "failed": 0,
            "regions": [],
            "source": "unset",
            "reason": (
                "OPENDATA_PREWARM_AREAS is not set, so this deployment has "
                "nominated no area to warm."
            ),
        }
    result = prewarm_areas(specs)
    result["source"] = "OPENDATA_PREWARM_AREAS"
    if not result["configured"] and not result["failed"]:
        # Set, but to something with no entry in it. Warming zero areas and
        # reporting a zero count would read as a batch that had nothing to do,
        # which is a different claim from "this setting holds no areas".
        result["reason"] = (
            "OPENDATA_PREWARM_AREAS is set but holds no lat,lon[,radius[,max_buildings]] entry."
        )
    return result


# ---- Background refresher ---------------------------------------------------
# Turns "fetch once, serve many" into "keep regions warm": every cycle the
# worker re-pulls a region that is still incomplete (for example one that came
# back without named places) using exponential backoff, so the cache heals
# without blocking any API request. Nothing here ever generates geometry.
_MIN_REFRESH_INTERVAL_S = 45.0
_last_refresh_ts: Dict[str, float] = {}
_worker_started = False
_worker_lock = threading.Lock()


def refresh_fallback_regions() -> Dict[str, Any]:
    """Single pass: re-pull cached regions that are still missing labels."""
    _load_snapshot()
    now = time.time()
    results = {"checked": 0, "upgraded": 0, "failed": 0}
    for key, entry in list(_REGION_STORE.items()):
        payload = entry.get("payload", {})
        counts = payload.get("counts", {}) or {}
        if counts.get("labels") or not counts.get("buildings"):
            continue
        if now - entry.get("cached_at", 0) < _MIN_REFRESH_INTERVAL_S:
            continue
        if now - _last_refresh_ts.get(key, 0) < 900:
            continue
        area = payload.get("area", {})
        lat, lon, radius = area.get("lat"), area.get("lon"), area.get("radius_m")
        if lat is None or lon is None:
            continue
        results["checked"] += 1
        _last_refresh_ts[key] = now
        try:
            fresh = fetch_area(lat, lon, radius, max(20, int(counts.get("buildings") or 220)))
            raw = {
                "buildings": fresh.buildings,
                "labels": fresh.labels,
                "source": fresh.provenance.provider,
                "provenance": fresh.provenance.as_dict(),
                "warnings": fresh.warnings,
                "fetched_at": fresh.provenance.retrieved_at,
                "_radius": radius,
            }
            upgraded = _project(lat, lon, raw)
            upgraded["region"] = key
            _REGION_STORE[key] = {
                "payload": upgraded,
                "cached_at": now,
                "fetched_at": upgraded.get("fetched_at"),
            }
            _persist_snapshot()
            results["upgraded"] += 1
        except Exception:  # noqa: BLE001
            results["failed"] += 1
    return results


def _start_refresher() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True

    def _loop() -> None:
        # Warm the nominated areas once, off the request path, before entering
        # the steady-state refresh loop.
        try:
            warmed = prewarm_areas_from_env()
            if warmed.get("configured"):
                print(
                    f"[opendata] prewarm: {warmed['warmed']} warmed, "
                    f"{warmed['already_cached']} already cached, {warmed['failed']} failed"
                )
        except Exception:  # noqa: BLE001 - warm-up never breaks the worker
            pass
        while True:
            try:
                refresh_fallback_regions()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(60)

    threading.Thread(target=_loop, name="opendata-refresher", daemon=True).start()


_start_refresher()