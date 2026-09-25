"""
Bhu-Drishti LiDAR Inspection Service.

Streams the documented point-cloud dataset (LAS-backed) to the new LiDAR
inspector UI. The dataset is an openly-licensed, deterministic synthetic
LiDAR sample (see data/sample_pointcloud/metadata.json) — it is served
with an explicit `demo: true` flag and never conflated with a real survey.

Pipeline: LAS (laspy) -> numpy arrays (cached) -> packed binary stream.
The same LAS file that documents the vertical cadastre ground truth
(B-17 levels, classifications) is the source of truth here.

Binary point record (stride = 20 bytes):
  x,y,z,gps_time : float32 (16 bytes)
  classification, intensity, return_no, num_returns : uint8 (4 bytes)
"""
from __future__ import annotations

import struct
import threading
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Response
from app.core.demo_gate import require_demo_mode
from app.core.lidar_coverage import NO_COVERAGE_MESSAGE

router = APIRouter(prefix="/lidar/inspect", tags=["lidar inspection"])

LAS_PATH = "/app/data/sample_pointcloud/airoli_s8_hero.las"
_MAGIC = b"BHDL"
_STRIDE = 20

# ASPRS classification codes present in the sample + tuned palette.
_CLASS_META: List[Dict[str, Any]] = [
    {"code": 2, "name": "ground", "label": "Ground", "color": "#3a2f2a"},
    {"code": 5, "name": "high_vegetation", "label": "High Vegetation", "color": "#2f8f5b"},
    {"code": 6, "name": "building", "label": "Building", "color": "#d8a13f"},
]

_lock = threading.Lock()
_cache: Dict[str, Any] = {}


def _return_numbers(las: Any, expected: int) -> np.ndarray:
    """Reads the ASPRS return-number bit out of each point's flags byte.

    Formats 0 and 5 carry no return number; those fall back to 1. Reading the
    real bit rather than assuming 1 matters because a multi-return capture
    would otherwise be flattened into a single return and silently miscounted.
    """
    try:
        fmt = int(las.header.point_format.id)
        if fmt in (0, 5):
            return np.ones(expected, dtype=np.uint8)
        rn = np.asarray(las.return_number)
        if len(rn) == expected:
            return rn.astype(np.uint8)
    except Exception:
        pass
    return np.ones(expected, dtype=np.uint8)


def _load_las() -> Dict[str, Any]:
    """Loads the LAS file once and caches numpy arrays + header metadata."""
    with _lock:
        if "loaded" in _cache:
            return _cache

        try:
            import laspy
        except Exception as exc:  # pragma: no cover - guarded import
            _cache["error"] = f"laspy unavailable: {exc}"
            return _cache

        if not __import__("os").path.exists(LAS_PATH):
            _cache["error"] = f"Point cloud file missing at {LAS_PATH}"
            return _cache

        try:
            las = laspy.read(LAS_PATH)
        except Exception as exc:
            _cache["error"] = f"Failed to read {LAS_PATH}: {exc}"
            return _cache

        xyz = np.vstack((las.x, las.y, las.z)).transpose().astype(np.float32)
        cls = np.asarray(las.classification).astype(np.uint8)
        gps = np.asarray(las.gps_time, dtype=np.float32)
        intensity_raw = np.asarray(las.intensity, dtype=np.float64)

        i_min = float(intensity_raw.min()) if len(intensity_raw) else 0.0
        i_max = float(intensity_raw.max()) if len(intensity_raw) else 0.0
        span = (i_max - i_min) or 1.0
        intensity = ((intensity_raw - i_min) / span * 255.0).clip(0, 255).astype(np.uint8)

        # This loader serves the uploaded LAS verbatim. It used to append
        # generated points on the way out: four synthetic hero floor slabs, a
        # fabricated "Epoch-2" storey at 18.0-21.5 m carrying a magic
        # intensity of 245 and return_number 2, and a full copy of every
        # precinct building's points from the demo property dataset. None of it
        # came from the survey. It inflated the reported point count, and the
        # fabricated 18.0-21.5 m band turned out to be the entire basis of the
        # inspector's "unauthorized construction detected" finding - the real
        # cloud stops at Z=18.06 m, so nothing in the file ever supported it.
        # A reader cannot tell which points were flown and which were invented,
        # so this returns the file and nothing else.
        rn_all = _return_numbers(las, len(xyz))

        b_min = [
            float(xyz[:, 0].min()) if len(xyz) else float(las.header.mins[0]),
            float(xyz[:, 1].min()) if len(xyz) else float(las.header.mins[1]),
            float(xyz[:, 2].min()) if len(xyz) else float(las.header.mins[2]),
        ]
        b_max = [
            float(xyz[:, 0].max()) if len(xyz) else float(las.header.maxs[0]),
            float(xyz[:, 1].max()) if len(xyz) else float(las.header.maxs[1]),
            float(xyz[:, 2].max()) if len(xyz) else float(las.header.maxs[2]),
        ]

        _cache.update(
            {
                "loaded": True,
                "path": LAS_PATH,
                "xyz": xyz,
                "cls": cls,
                "gps": gps,
                "intensity": intensity,
                "return_number": rn_all,
                "intensity_range": [i_min, i_max],
                "bounds": {
                    "min": b_min,
                    "max": b_max,
                },
                "point_count": int(len(xyz)),
                "format": f"LAS {las.header.major_version}.{las.header.minor_version}",
                "point_format": int(las.header.point_format.id),
                "epsg": 32643,
            }
        )
        return _cache


def _class_label(code: int) -> str:
    for m in _CLASS_META:
        if m["code"] == code:
            return m["label"]
    return "Unclassified"


def _hero_ground_truth() -> Dict[str, Any]:
    """Ground truth tied to the product property model (hero B-17)."""
    try:
        from app.api.v1.properties import _DATASET_CACHE
    except Exception:
        return {}

    structure = _DATASET_CACHE.get("hero_structure") or {}
    parcel = _DATASET_CACHE.get("hero_parcel") or {}

    def ring(geo: Any) -> List[List[float]]:
        try:
            return [[float(c[0]), float(c[1])] for c in geo["coordinates"][0]]
        except Exception:
            return []

    layers = []
    for lv in _DATASET_CACHE.get("levels", []) or []:
        layers.append(
            {
                "level_code": lv.get("level_code"),
                "floor_number": lv.get("floor_number"),
                "name": lv.get("name"),
                "level_type": lv.get("level_type"),
                "min_z": float(lv.get("min_z", 0.0)),
                "max_z": float(lv.get("max_z", 0.0)),
            }
        )

    surrounding = []
    precinct_list = _DATASET_CACHE.get("precinct_buildings", [])
    if precinct_list:
        for b in precinct_list:
            fp = ring(b.get("footprint_geojson"))
            if not fp:
                x, y, w, h = b["x"], b["y"], b["w"], b["h"]
                fp = [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]]
            
            px, py, pw, ph = b["x"], b["y"], b["w"], b["h"]
            p_ring = [[px - 6.0, py - 6.0], [px + pw + 6.0, py - 6.0], [px + pw + 6.0, py + ph + 6.0], [px - 6.0, py + ph + 6.0], [px - 6.0, py - 6.0]]
            
            floors = b.get("floors", 4)
            ht = float(b.get("height_m", floors * 3.5))
            fl_h = ht / floors
            b_levels = b.get("levels") or []
            if not b_levels:
                if b.get("basements_count", 0) > 0:
                    b_levels.append({"level_code": "B1", "floor_number": -1, "name": "Basement", "level_type": "BASEMENT", "min_z": -3.5, "max_z": 0.0})
                b_levels.append({"level_code": "G", "floor_number": 0, "name": "Ground", "level_type": "GROUND", "min_z": 0.0, "max_z": round(fl_h, 2)})
                for k in range(1, floors):
                    b_levels.append({
                        "level_code": f"L{k:02d}" if floors >= 10 else f"L{k}",
                        "floor_number": k,
                        "name": f"Floor {k}",
                        "level_type": "FLOOR",
                        "min_z": round(fl_h * k, 2),
                        "max_z": round(fl_h * (k + 1), 2),
                    })
                
            surrounding.append(
                {
                    "ulpin": b.get("ulpin"),
                    "survey_number": b.get("code", ""),
                    "building_code": b.get("code"),
                    "building_name": b.get("name"),
                    "proposed_3d_id": b.get("proposed_3d_id"),
                    "units": b.get("units", []),
                    "units_count": len(b.get("units", [])),
                    "ring": p_ring,
                    "footprint": fp,
                    "height_m": ht,
                    "floors_count": floors,
                    "levels": b_levels,
                    "type": b.get("type", "tower"),
                    "status": b.get("status", "DEMO_STANDARD"),
                    "risk_level": b.get("risk_level", "LOW"),
                    "fsi": b.get("fsi", 1.5),
                }
            )
    else:
        for p in _DATASET_CACHE.get("surrounding_parcels", []) or []:
            surrounding.append(
                {
                    "ulpin": p.get("ulpin"),
                    "survey_number": p.get("survey_number", ""),
                    "building_code": p.get("survey_number", ""),
                    "building_name": f"Parcel {p.get('survey_number', '')}",
                    "proposed_3d_id": None,
                    "units": [],
                    "units_count": 0,
                    "ring": ring(p.get("polygon_geojson")),
                    "footprint": [],
                    "height_m": 0.0,
                    "floors_count": 0,
                    "levels": [],
                }
            )

    hero_units = _DATASET_CACHE.get("units", [])
    return {
        "ulpin": parcel.get("ulpin", "12345678901234"),
        "proposed_3d_id": "12345678901234/UB17-G-001-A",
        "parcel_ring": ring(parcel.get("polygon_geojson")),
        "building_code": structure.get("building_code", "B-17"),
        "building_name": structure.get("name", "Shree Ganesh CHS (Building B-17)"),
        "footprint": ring(structure.get("footprint_geojson")),
        "height_m": float(structure.get("height_m", 18.0)),
        "floors_count": int(structure.get("floors_count", 5)),
        "levels": layers,
        "units": hero_units,
        "units_count": len(hero_units),
        "surrounding_parcels": surrounding,
    }


@router.get("/scene")
def get_scene() -> Dict[str, Any]:
    """Scene metadata: dataset provenance, stats, classification palette, ground truth."""
    # The dataset behind this is generated, so it is demo data like the rest of
    # the Airoli showcase. It was reachable with the gate shut: this endpoint
    # builds its provenance block from literals, so with no dataset loaded it
    # still answered 200 with a full scene description and a `source` string
    # naming a file nobody produced. Gating it means a deployment that serves
    # only ingested records says so, instead of describing a survey that was
    # never flown.
    require_demo_mode("LiDAR inspection scene", note=NO_COVERAGE_MESSAGE)
    cache = _load_las()
    if "error" in cache:
        raise HTTPException(status_code=503, detail=cache["error"])

    bounds = cache["bounds"]
    xyz = cache["xyz"]
    cls = cache["cls"]

    class_counts = []
    present = set(cls.tolist())
    for m in _CLASS_META:
        class_counts.append(
            {
                **m,
                "count": int(np.count_nonzero(cls == m["code"])),
                "present": m["code"] in present,
            }
        )

    span = [
        bounds["max"][0] - bounds["min"][0],
        bounds["max"][1] - bounds["min"][1],
        bounds["max"][2] - bounds["min"][2],
    ]
    extent_x = span[0] or 1.0
    extent_y = span[1] or 1.0

    return {
        "dataset": {
            "id": "airoli-s8-hero-lidar",
            "name": "Airoli Sector 8 Hero Case — Raw LiDAR (B-17 Vertical Cadastre)",
            # Was "alms:airoli_s8_hero.las", which read like a delivery from a
            # survey vendor. No ALMS delivery ever happened: this file was
            # generated by this project, and the dataset's own metadata.json says
            # so. A source string is the one field a reader trusts before
            # reading anything else, so it is the last place to be vague.
            "source": "Bhu-Drishti 3D evaluation dataset (generated, seed 271828)",
            "demo": True,
            "demo_note": "Synthetic demo LiDAR (deterministic seed 271828). No airborne survey captured.",
            "license": "Open demo data — generated for evaluation",
            "crs": {"epsg": 32643, "name": "WGS 84 / UTM zone 43N (projected)", "local_frame_offset_m": [0.0, 0.0]},
            "format": cache["format"],
            "point_format": cache["point_format"],
            "attributes": ["x", "y", "z", "classification", "intensity", "gps_time"],
            "has_rgb": False,
            "intensity_range": cache["intensity_range"],
            # The shipped capture is a single pass. Every point in it is
            # return 1, so there is no repeat-observation delta to measure and
            # no change-detection claim can be supported from this file.
            "epochs_available": 1,
            "multi_epoch": False,
            "multi_epoch_note": (
                "Single-pass capture: all returns are return 1. No second-epoch "
                "survey exists for this scene, so no vertical-change or "
                "unauthorized-construction finding can be derived from it."
            ),
        },
        "stats": {
            "point_count": cache["point_count"],
            "bounds": bounds,
            "span_m": [round(v, 2) for v in span],
            "center": [
                round((bounds["min"][0] + bounds["max"][0]) / 2, 2),
                round((bounds["min"][1] + bounds["max"][1]) / 2, 2),
                round((bounds["min"][2] + bounds["max"][2]) / 2, 2),
            ],
            "density_pts_m2": round(cache["point_count"] / (extent_x * extent_y), 1),
            "classifications": class_counts,
        },
        "ground_truth": _hero_ground_truth(),
    }


@router.get("/points")
def get_points(
    step: int = Query(1, ge=1, le=16),
    classes: Optional[str] = Query(None, description="Comma-separated class codes to include"),
    region: Optional[str] = Query(None, description="xmin,ymin,xmax,ymax in local metres"),
) -> Response:
    """Streams packed point records with subsampling + class/region filtering."""
    require_demo_mode("LiDAR inspection points", note=NO_COVERAGE_MESSAGE)
    cache = _load_las()
    if "error" in cache:
        raise HTTPException(status_code=503, detail=cache["error"])

    cls_all = cache["cls"]
    n = len(cls_all)
    mask = np.ones(n, dtype=bool)

    if classes:
        wanted = {int(c.strip()) for c in classes.split(",") if c.strip().isdigit()}
        if not wanted:
            raise HTTPException(status_code=422, detail="classes must be comma-separated class codes")
        mask &= np.isin(cls_all, list(wanted))

    if region:
        parts = [p.strip() for p in region.split(",")]
        if len(parts) != 4:
            raise HTTPException(status_code=422, detail="region must be xmin,ymin,xmax,ymax")
        try:
            xmin, ymin, xmax, ymax = (float(p) for p in parts)
        except ValueError:
            raise HTTPException(status_code=422, detail="region values must be numeric")
        xyz = cache["xyz"]
        mask &= (
            (xyz[:, 0] >= xmin) & (xyz[:, 0] <= xmax) &
            (xyz[:, 1] >= ymin) & (xyz[:, 1] <= ymax)
        )

    indices = np.nonzero(mask)[0]
    flagged = indices[::step]

    dtype = np.dtype(
        [
            ("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("gps", "<f4"),
            ("cls", "u1"), ("intensity", "u1"), ("rn", "u1"), ("nret", "u1"),
        ]
    )
    rec = np.zeros(len(flagged), dtype=dtype)
    xyz = cache["xyz"]
    rec["x"] = xyz[flagged, 0]
    rec["y"] = xyz[flagged, 1]
    rec["z"] = xyz[flagged, 2]
    rec["gps"] = cache["gps"][flagged]
    rec["cls"] = cls_all[flagged]
    rec["intensity"] = cache["intensity"][flagged]
    rn_all = cache.get("return_number")
    rec["rn"] = rn_all[flagged] if rn_all is not None and len(rn_all) == len(xyz) else 1
    rec["nret"] = 1

    header = struct.pack("<4sII", _MAGIC, _STRIDE, len(flagged))
    body = rec.tobytes()

    return Response(
        content=header + body,
        media_type="application/octet-stream",
        headers={
            "X-Point-Count": str(len(flagged)),
            "X-Class-Codes": ",".join(str(c) for c in np.unique(cls_all[flagged]).tolist()),
            "Cache-Control": "no-store",
        },
    )