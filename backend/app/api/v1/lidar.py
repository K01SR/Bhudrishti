import struct
import io
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Response, Query
from app.api.v1.properties import _DATASET_CACHE
from app.core.demo_gate import require_demo_mode
from app.core.lidar_coverage import NO_COVERAGE_MESSAGE

router = APIRouter(prefix="/lidar", tags=["lidar"])

def _get_all_buildings_metadata() -> List[Dict[str, Any]]:
    """Build list of all 13 buildings in the precinct with metadata."""
    hero = _DATASET_CACHE.get("hero_structure", {})
    hero_bld = {
        "code": hero.get("building_code", "B-17"),
        "name": hero.get("name", "Shree Ganesh CHS (Building B-17)"),
        "type": "tower",
        "floors": hero.get("floors_count", 5),
        "height_m": hero.get("height_m", 18.0),
        "x": 145.0,
        "y": 144.0,
        "w": 30.0,
        "h": 17.0,
        "fsi": hero.get("calculated_fsi", 1.80),
        "status": "DEMO_STANDARD",
        "risk_level": "LOW",
        "units_count": 21,
        "basements_count": 1,
        "ulpin": "12345678901234",
        "is_hero": True,
        "footprint": hero.get("footprint_geojson", {}).get("coordinates", [[]])[0] if hero.get("footprint_geojson") else [],
        "levels": [
            {"level_code": "B1", "min_z": -3.5, "max_z": 0.0},
            {"level_code": "G", "min_z": 0.0, "max_z": 3.6},
            {"level_code": "L1", "min_z": 3.6, "max_z": 7.2},
            {"level_code": "L2", "min_z": 7.2, "max_z": 10.8},
            {"level_code": "L3", "min_z": 10.8, "max_z": 14.4},
            {"level_code": "L4", "min_z": 14.4, "max_z": 18.0},
        ],
    }

    buildings = [hero_bld]

    precinct_list = _DATASET_CACHE.get("precinct_buildings", [])
    for b in precinct_list:
        floors = b.get("floors", 4)
        ht = float(b.get("height_m", floors * 3.5))
        fl_h = ht / floors
        levels = []
        if b.get("basements_count", 0) > 0:
            levels.append({"level_code": "B1", "min_z": -3.5, "max_z": 0.0})
        levels.append({"level_code": "G", "min_z": 0.0, "max_z": round(fl_h, 2)})
        for k in range(1, floors):
            levels.append({
                "level_code": f"L{k:02d}" if floors >= 10 else f"L{k}",
                "min_z": round(fl_h * k, 2),
                "max_z": round(fl_h * (k + 1), 2),
            })

        fp = b.get("footprint_geojson", {}).get("coordinates", [[]])[0] if b.get("footprint_geojson") else []
        if not fp:
            x, y, w, h = b["x"], b["y"], b["w"], b["h"]
            fp = [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]]

        buildings.append({
            "code": b.get("code"),
            "name": b.get("name"),
            "type": b.get("type", "tower"),
            "floors": floors,
            "height_m": ht,
            "x": float(b.get("x", 0)),
            "y": float(b.get("y", 0)),
            "w": float(b.get("w", 20)),
            "h": float(b.get("h", 20)),
            "fsi": float(b.get("fsi", 1.5)),
            "status": b.get("status", "DEMO_STANDARD"),
            "risk_level": b.get("risk_level", "LOW"),
            "units_count": b.get("units_count", floors * 4),
            "basements_count": b.get("basements_count", 0),
            "ulpin": b.get("ulpin", ""),
            "is_hero": False,
            "footprint": fp,
            "levels": levels,
        })

    return buildings


def _generate_vectorized_lidar_points(footprint: List[List[float]], height_m: float, floors: int = 5) -> List[Dict[str, Any]]:
    """Vectorized generator for realistic classified LiDAR point clouds using NumPy."""
    import numpy as np

    xs = [p[0] for p in footprint] if footprint else [145.0, 175.0]
    ys = [p[1] for p in footprint] if footprint else [145.0, 170.0]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # 1. Ground points (class 2)
    n_ground = 1800
    gx = np.random.uniform(min_x - 12.0, max_x + 12.0, n_ground)
    gy = np.random.uniform(min_y - 12.0, max_y + 12.0, n_ground)
    gz = np.random.normal(0.0, 0.04, n_ground)
    g_int = np.random.uniform(70.0, 110.0, n_ground)

    # 2. Roof returns (class 6)
    n_roof = 2200
    rx = np.random.uniform(min_x, max_x, n_roof)
    ry = np.random.uniform(min_y, max_y, n_roof)
    rz = np.random.normal(height_m, 0.06, n_roof)
    r_int = np.random.uniform(180.0, 230.0, n_roof)

    # 3. Wall returns (class 3)
    segments = []
    if len(footprint) >= 2:
        for i in range(len(footprint) - 1):
            segments.append((footprint[i], footprint[i + 1]))
    if not segments:
        segments = [
            ([min_x, min_y], [max_x, min_y]),
            ([max_x, min_y], [max_x, max_y]),
            ([max_x, max_y], [min_x, max_y]),
            ([min_x, max_y], [min_x, min_y]),
        ]

    n_wall = 2500
    pts_per_seg = max(50, n_wall // len(segments))
    wx_l, wy_l, wz_l = [], [], []
    for p1, p2 in segments:
        alphas = np.random.uniform(0.0, 1.0, pts_per_seg)
        wx_l.append(p1[0] + alphas * (p2[0] - p1[0]) + np.random.normal(0, 0.05, pts_per_seg))
        wy_l.append(p1[1] + alphas * (p2[1] - p1[1]) + np.random.normal(0, 0.05, pts_per_seg))
        wz_l.append(np.random.uniform(0.0, height_m, pts_per_seg))
    wx = np.concatenate(wx_l)
    wy = np.concatenate(wy_l)
    wz = np.concatenate(wz_l)
    w_int = np.random.uniform(110.0, 160.0, len(wx))

    # Assemble combined dictionaries
    points: List[Dict[str, Any]] = []
    for x, y, z, it in zip(gx, gy, gz, g_int):
        points.append({
            "x": round(float(x), 3), "y": round(float(y), 3), "z": round(float(z), 3),
            "classification": 2, "intensity": round(float(it), 1),
            "r": 139, "g": 115, "b": 85,
        })
    for x, y, z, it in zip(rx, ry, rz, r_int):
        points.append({
            "x": round(float(x), 3), "y": round(float(y), 3), "z": round(float(z), 3),
            "classification": 6, "intensity": round(float(it), 1),
            "r": 220, "g": 38, "b": 38,
        })
    for x, y, z, it in zip(wx, wy, wz, w_int):
        points.append({
            "x": round(float(x), 3), "y": round(float(y), 3), "z": round(float(z), 3),
            "classification": 3, "intensity": round(float(it), 1),
            "r": 37, "g": 99, "b": 235,
        })

    return points


def _resolve_points_and_meta(building_code: Optional[str] = None, ulpin: Optional[str] = None):
    """Resolve points, bounds, center, footprint, and levels for chosen building or all."""

    # Case 0: Open-data AREA scan — ULPIN format AREA-<lat>_<lon>_<radius>.
    if ulpin and ulpin.upper().startswith("AREA-"):
        from app.opendata import service as opendata_service
        try:
            lat_s, lon_s, radius_s = ulpin[5:].split("_")
            lat = float(lat_s)
            lon = float(lon_s)
            radius = int(float(radius_s))
        except (ValueError, IndexError):
            pass
        else:
            return opendata_service.area_lidar_points(lat, lon, radius, ulpin=ulpin)

    all_blds = _get_all_buildings_metadata()
    by_ulpin = _DATASET_CACHE.get("synthetic_lidar_points_by_ulpin", {})
    hero_points = _DATASET_CACHE.get("synthetic_lidar_points_classified", [])

    # Case 1: ALL / PRECINCT Wide Area Survey
    if building_code and building_code.upper() in ("ALL", "PRECINCT", "WIDE"):
        combined_points = []
        # Subsample hero points
        step_hero = max(1, len(hero_points) // 6000)
        combined_points.extend(hero_points[::step_hero])

        # Subsample points from each precinct building
        for ulp, pts in by_ulpin.items():
            if pts:
                step_bld = max(1, len(pts) // 2500)
                combined_points.extend(pts[::step_bld])

        if not combined_points:
            combined_points = hero_points

        min_x = min(p["x"] for p in combined_points)
        max_x = max(p["x"] for p in combined_points)
        min_y = min(p["y"] for p in combined_points)
        max_y = max(p["y"] for p in combined_points)
        min_z = min(p["z"] for p in combined_points)
        max_z = max(p["z"] for p in combined_points)

        meta = {
            "building_code": "ALL",
            "building_name": "Whole Precinct Survey (Airoli Sector 8 - Wide Area Scan)",
            "ulpin": "MH-THN-AIR-SEC08-ALL",
            "type": "precinct",
            "floors": 20,
            "height_m": round(max_z, 1),
            "status": "DEMO_STANDARD",
            "risk_level": "LOW",
            "point_count": len(combined_points),
            "bounds": {"min": [min_x, min_y, min_z], "max": [max_x, max_y, max_z]},
            "center": [(min_x + max_x) / 2, (min_y + max_y) / 2, (min_z + max_z) / 2],
            "building_footprint": [],
            "parcel_boundary": [[30, 30], [380, 30], [380, 380], [30, 380], [30, 30]],
            "levels": [
                {"level_code": "B1", "min_z": -3.5, "max_z": 0.0},
                {"level_code": "G", "min_z": 0.0, "max_z": 3.6},
                {"level_code": "L1-L5", "min_z": 3.6, "max_z": 18.0},
                {"level_code": "L6-L10", "min_z": 18.0, "max_z": 35.0},
                {"level_code": "L11-L20", "min_z": 35.0, "max_z": 70.0},
            ],
            "available_buildings": [
                {
                    "code": "ALL",
                    "name": "🌐 Whole Precinct (Airoli Sector 8 - Wide Scan)",
                    "ulpin": "MH-THN-AIR-SEC08-ALL",
                    "type": "precinct",
                    "floors": 20,
                    "height_m": 70.0,
                    "status": "SURVEYED",
                    "risk_level": "LOW",
                    "point_count": len(combined_points),
                }
            ] + [
                {
                    "code": b["code"],
                    "name": b["name"],
                    "ulpin": b["ulpin"],
                    "type": b["type"],
                    "floors": b["floors"],
                    "height_m": b["height_m"],
                    "status": b["status"],
                    "risk_level": b["risk_level"],
                    "is_hero": b.get("is_hero", False),
                }
                for b in all_blds
            ],
        }
        return combined_points, meta

    # Case 2: Specific building by code or ULPIN
    target_bld = None
    if building_code and building_code.upper() not in ("ALL", "PRECINCT", "WIDE"):
        for b in all_blds:
            if b["code"].upper() == building_code.upper():
                target_bld = b
                break
    if not target_bld and ulpin:
        for b in all_blds:
            if b["ulpin"] == ulpin or b.get("code", "").upper() == ulpin.upper():
                target_bld = b
                break

    # If building is not in precinct dataset, generate dynamic LiDAR on-demand
    if not target_bld and (ulpin or building_code):
        req_id = ulpin or building_code
        clean_code = f"BLD-{req_id[-6:]}" if len(req_id) >= 6 else "BLD-01"
        floors = 6
        height_m = 21.0
        footprint = [
            [145.0, 145.0],
            [175.0, 145.0],
            [175.0, 170.0],
            [145.0, 170.0],
            [145.0, 145.0],
        ]
        levels = [
            {"level_code": f"L{k:02d}" if k > 0 else "G", "min_z": round(k * 3.5, 1), "max_z": round((k + 1) * 3.5, 1)}
            for k in range(floors)
        ]
        target_bld = {
            "code": clean_code,
            "name": f"3D Cadastral Twin ({req_id})",
            "type": "tower",
            "floors": floors,
            "height_m": height_m,
            "x": 145.0,
            "y": 145.0,
            "w": 30.0,
            "h": 25.0,
            "fsi": 1.75,
            "status": "DEMO_STANDARD",
            "risk_level": "LOW",
            "units_count": 24,
            "basements_count": 0,
            "ulpin": req_id,
            "is_hero": False,
            "footprint": footprint,
            "levels": levels,
        }
        points = _generate_vectorized_lidar_points(footprint, height_m, floors)
    elif target_bld:
        if target_bld.get("is_hero") or target_bld["code"] == "B-17" or target_bld["ulpin"] == "12345678901234":
            points = hero_points
        else:
            points = by_ulpin.get(target_bld["ulpin"])
            if not points:
                points = _generate_vectorized_lidar_points(
                    target_bld.get("footprint", [[145.0, 145.0], [175.0, 145.0], [175.0, 170.0], [145.0, 170.0], [145.0, 145.0]]),
                    target_bld.get("height_m", 18.0),
                    target_bld.get("floors", 5)
                )
    else:
        target_bld = all_blds[0]
        points = hero_points

    min_x = min(p["x"] for p in points)
    max_x = max(p["x"] for p in points)
    min_y = min(p["y"] for p in points)
    max_y = max(p["y"] for p in points)
    min_z = min(p["z"] for p in points)
    max_z = max(p["z"] for p in points)

    fp = target_bld.get("footprint", [])
    x, y, w, h = target_bld["x"], target_bld["y"], target_bld["w"], target_bld["h"]
    parcel_boundary = [
        [x - 6.0, y - 6.0],
        [x + w + 6.0, y - 6.0],
        [x + w + 6.0, y + h + 6.0],
        [x - 6.0, y + h + 6.0],
        [x - 6.0, y - 6.0],
    ]

    meta = {
        "building_code": target_bld["code"],
        "building_name": target_bld["name"],
        "ulpin": target_bld["ulpin"],
        "type": target_bld["type"],
        "floors": target_bld["floors"],
        "height_m": target_bld["height_m"],
        # The cloud below is a modelled point field built from this precinct's
        # generated footprints, not an airborne acquisition. `status` and
        # `risk_level` therefore describe the synthetic dataset's own bookkeeping
        # and carry no survey or enforcement meaning.
        "data_provenance": "demo-generated",
        "point_cloud_kind": "MODELLED",
        "authoritative": False,
        "status_note": (
            "Status and risk level come from the generated demo dataset. No "
            "survey of this building has been performed."
        ),
        "point_count": len(points),
        "bounds": {"min": [min_x, min_y, min_z], "max": [max_x, max_y, max_z]},
        "center": [float((min_x + max_x) / 2), float((min_y + max_y) / 2), float((min_z + max_z) / 2)],
        "building_footprint": fp,
        "parcel_boundary": parcel_boundary,
        "levels": target_bld.get("levels", []),
        "available_buildings": [
            {
                "code": "ALL",
                "name": "🌐 Whole Precinct (Airoli Sector 8 - Wide Scan)",
                "ulpin": "MH-THN-AIR-SEC08-ALL",
                "type": "precinct",
                "floors": 20,
                "height_m": 70.0,
                "status": "SURVEYED",
                "risk_level": "LOW",
            }
        ] + [
            {
                "code": b["code"],
                "name": b["name"],
                "ulpin": b["ulpin"],
                "type": b["type"],
                "floors": b["floors"],
                "height_m": b["height_m"],
                "status": b["status"],
                "risk_level": b["risk_level"],
                "is_hero": b.get("is_hero", False),
            }
            for b in all_blds
        ],
    }
    return points, meta


@router.get("/pointcloud")
def get_lidar_pointcloud(
    building_code: Optional[str] = Query(None, description="Building code (e.g. B-01, B-17, ALL)"),
    ulpin: Optional[str] = Query(None, description="Property ULPIN")
):
    # These points come from the generated Airoli dataset, so they are demo data
    # and are gated like the rest of it. The metadata beside them is built from
    # literals, so with the gate shut this used to answer with a confident
    # building name, a permitted FSI and a point count for a survey nobody flew.
    require_demo_mode("LiDAR point cloud", note=NO_COVERAGE_MESSAGE)
    points, meta = _resolve_points_and_meta(building_code=building_code, ulpin=ulpin)
    
    # Calculate classification breakdown
    class_counts = {}
    for p in points:
        c = p.get("classification", 2)
        class_counts[c] = class_counts.get(c, 0) + 1

    return {
        **meta,
        "classifications": {
            "ground": {"count": class_counts.get(2, 0), "color": "#8B7355"},
            "vegetation": {"count": class_counts.get(5, 0), "color": "#2F8F5B"},
            "roof": {"count": class_counts.get(6, 0), "color": "#DC2626"},
            "wall": {"count": class_counts.get(3, 0), "color": "#2563EB"}
        },
        "points": points,
    }


@router.get("/pointcloud/binary")
def get_lidar_pointcloud_binary(
    building_code: Optional[str] = Query(None, description="Building code (e.g. B-01, B-17, ALL)"),
    ulpin: Optional[str] = Query(None, description="Property ULPIN")
):
    require_demo_mode("LiDAR point cloud", note=NO_COVERAGE_MESSAGE)
    points, meta = _resolve_points_and_meta(building_code=building_code, ulpin=ulpin)
    
    # Pack into binary buffer
    # Format: [x, y, z, classification, intensity, r, g, b] as 8 floats
    buffer = io.BytesIO()
    for p in points:
        buffer.write(struct.pack('<8f', 
            float(p['x']), float(p['y']), float(p['z']), 
            float(p.get('classification', 2)), float(p.get('intensity', 100)), 
            float(p.get('r', 128)), float(p.get('g', 128)), float(p.get('b', 128))
        ))
    
    return Response(
        content=buffer.getvalue(),
        media_type="application/octet-stream",
        headers={
            "X-Point-Count": str(len(points)),
            "X-Building-Code": str(meta.get("building_code", "B-17")),
            "X-Building-Height": str(meta.get("height_m", 18.0)),
        }
    )
