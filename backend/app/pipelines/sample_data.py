"""
Realistic LiDAR / ortho sample dataset generation (Airoli Sector 8 Hero Case).

Synthesises a deterministic, spatially-coherent point cloud over the Airoli
sector domain so the REAL ingestion -> extraction -> floor segmentation ->
vertical delineation path runs end-to-end on an actual ``.las`` file (not an
in-memory array). Metadata, ground-truth footprints and provenance are written
alongside the cloud so every metric produced by the ML pipelines can be
evaluated against a known reality.

All coordinates are in the local cadastral frame used across the platform
(B-17 centred on [160, 152.5], ground plane at z = 0). The ``metadata.json``
records the real-world EPSG:32643 (UTM 43N) offset applied for export.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, List

import numpy as np

try:
    import laspy
except ImportError:  # pragma: no cover
    laspy = None

DEFAULT_SAMPLE_DIR = "/app/data/sample_pointcloud"


def default_sample_dir() -> str:
    """Resolve the LiDAR sample directory for the current runtime.

    Prefers the docker bind-mount path (``/app/data/sample_pointcloud``);
    falls back to the repository-local ``./data/sample_pointcloud`` so the
    same sample dataset is shared by the docker stack (which mounts
    ``./data:/app/data``) and native/manual runs.
    """
    mounted = "/app/data/sample_pointcloud"
    try:
        os.makedirs(mounted, exist_ok=True)
        probe = os.path.join(mounted, ".probe")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        return mounted
    except Exception:
        pass
    repo_local = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "data",
        "sample_pointcloud",
    )
    return repo_local

# ---- Airoli sector domain ---------------------------------------------------
DOMAIN = {"x": (120.0, 200.0), "y": (125.0, 185.0)}
HERO_B17 = {
    "building_code": "B-17",
    "footprint": [[145.0, 144.0], [175.0, 144.0], [175.0, 161.0], [145.0, 161.0]],
    "ground_z": 0.0,
    "levels": [
        {"code": "B1", "min_z": -3.5, "max_z": 0.0},
        {"code": "G", "min_z": 0.0, "max_z": 3.6},
        {"code": "L01", "min_z": 3.6, "max_z": 7.2},
        {"code": "L02", "min_z": 7.2, "max_z": 10.8},
        {"code": "L03", "min_z": 10.8, "max_z": 14.4},
        {"code": "L04", "min_z": 14.4, "max_z": 18.0},
    ],
}

# Contextual fabric (aligned with the visual world build): (x0, y0, x1, y1, h)
_FABRIC = [
    (150, 132, 160, 138, 12.5), (165, 128, 178, 138, 9.5), (128, 128, 142, 140, 15.5),
    (178, 140, 190, 150, 10.8), (118, 140, 128, 152, 11.2), (120, 150, 132, 161, 13.8),
    (132, 161, 145, 169, 8.4), (175, 161, 186, 172, 9.9), (150, 161, 165, 170, 12.0),
    (186, 172, 198, 180, 10.5), (140, 169, 150, 180, 7.8), (162, 170, 176, 182, 14.2),
    (126, 161, 139, 170, 6.9), (176, 150, 184, 161, 8.8), (142, 138, 150, 144, 9.6),
    (160, 138, 165, 144, 10.2),
]
GROVE_ANCHORS = [(150, 154, 8), (158, 148, 7), (168, 148, 9), (130, 150, 6), (180, 158, 7)]


def _poly_pts(footprint: List[List[float]], n_per_side: int = 6) -> np.ndarray:
    """Sample points along a footprint polygon ring."""
    ring = footprint + [footprint[0]]
    segs: List[np.ndarray] = []
    for (x0, y0), (x1, y1) in zip(ring[:-1], ring[1:]):
        ts = np.linspace(0, 1, n_per_side, endpoint=False)
        segs.append(np.column_stack([x0 + (x1 - x0) * ts, y0 + (y1 - y0) * ts]))
    return np.vstack(segs)


def generate_point_cloud(seed: int = 271828, points_per_m2: float = 6.0) -> np.ndarray:
    """Returns an (N, 4) array: x, y, z, classification (2/5/6)."""
    rng = np.random.default_rng(seed)
    x0, x1 = DOMAIN["x"]
    y0, y1 = DOMAIN["y"]

    cols: List[np.ndarray] = []

    def emit(p: np.ndarray, z: np.ndarray, cls: int) -> None:
        p = np.asarray(p, dtype=np.float64)
        z = np.asarray(z, dtype=np.float64).reshape(-1)
        n = len(p)
        cols.append(np.column_stack([p[:, 0], p[:, 1], z, np.full(n, cls, dtype=np.uint8)]))

    # 1) Ground returns (class 2) with gentle relief + gaussian sensor noise.
    gx, gy = np.meshgrid(
        np.arange(x0, x1, 0.5), np.arange(y0, y1, 0.5)
    )
    gz = (
        0.15 * np.sin(gx / 9.0) * np.cos(gy / 7.0)
        + 0.08 * np.sin((gx + gy) / 5.0)
        + rng.normal(0.0, 0.03, gx.shape)
    )
    emit(np.column_stack([gx.ravel(), gy.ravel()]), gz.ravel(), 2)

    def in_poly(p: np.ndarray, ring: List[List[float]]) -> np.ndarray:
        from shapely.geometry import Point
        from shapely.geometry.polygon import Polygon
        poly = Polygon(ring)
        return np.array([poly.contains(Point(px, py)) for px, py in p])

    # 2) Hero B-17 building returns (class 6): walls + per-floor slabs + roof.
    for level in HERO_B17["levels"]:
        z_rng = (level["min_z"], level["max_z"])
        slab = _poly_pts(HERO_B17["footprint"])
        n_slab = max(40, int(30 * len(slab)))
        idx = rng.integers(0, len(slab), n_slab)
        emit(slab[idx], rng.uniform(*z_rng, n_slab), 6)
    roof = _poly_pts(HERO_B17["footprint"])
    roar = rng.uniform(17.6, 18.2, len(roof) * 3)
    zr = np.zeros(len(roof) * 3)
    zr[:] = 18.0
    emit(np.tile(roof, (3, 1)), zr + rng.normal(0, 0.03, len(roof) * 3), 6)

    # 3) Contextual buildings (class 6).
    for (fx0, fy0, fx1, fy1, h) in _FABRIC:
        fprint = [[fx0, fy0], [fx1, fy0], [fx1, fy1], [fx0, fy1]]
        peri = _poly_pts(fprint)
        n_peri = max(25, int(10 * len(peri)))
        idx = rng.integers(0, len(peri), n_peri)
        emit(peri[idx], rng.uniform(0.0, h, n_peri), 6)
        fill = np.random.default_rng(int((fx0 + fy0 + fx1 + fy1) * 100)).uniform(
            fx0 + 0.4, fx1 - 0.4, (8, 2)
        )
        emit(fill, rng.uniform(h - 0.4, h + 0.2, 8), 6)

    # 4) Vegetation canopies (class 5).
    for (ax, ay, r) in GROVE_ANCHORS:
        n_pts = int(np.pi * r * r * 2.0)
        ang = rng.uniform(0, 2 * np.pi, n_pts)
        rad = rng.uniform(0, r, n_pts)
        px = ax + rad * np.cos(ang)
        py = ay + rad * np.sin(ang)
        hz = rng.uniform(1.5, 5.0, n_pts)
        emit(np.column_stack([px, py]), hz + 0.02 * rng.normal(0, 1, n_pts), 5)

    cloud = np.vstack(cols)
    # Sub-sample to requested density for a tractable demo file.
    total_area = (x1 - x0) * (y1 - y0)
    target = int(total_area * points_per_m2)
    if len(cloud) > target:
        keep = rng.choice(len(cloud), target, replace=False)
        cloud = cloud[keep]
    cloud = cloud[np.lexsort((cloud[:, 2], cloud[:, 1], cloud[:, 0]))]
    return cloud


def write_las(cloud: np.ndarray, path: str) -> Dict[str, Any]:
    """Writes the point cloud as LAS 1.2 (point format 3) with classifications."""
    if laspy is None:
        raise RuntimeError("laspy is required to write LAS/LAZ sample point clouds.")

    x = cloud[:, 0].astype(np.float64)
    y = cloud[:, 1].astype(np.float64)
    z = cloud[:, 2].astype(np.float64)
    cls = cloud[:, 3].astype(np.uint8)

    las = laspy.create(point_format=3, file_version="1.2")
    n = len(x)
    las.x = x
    las.y = y
    las.z = z
    las.classification = cls
    las.intensity = np.uint16(np.clip(50 + 40 * z / max(float(np.nanmax(z)), 1.0), 0, 65535))
    las.return_number = np.uint8(np.ones(n, dtype=np.uint8))
    las.number_of_returns = np.uint8(np.ones(n, dtype=np.uint8))
    las.gps_time = np.arange(n, dtype=np.float64)
    las.header.scales = np.array([0.01, 0.01, 0.01])
    las.header.offsets = np.array([0.0, 0.0, 0.0])
    las.write(path)
    return {
        "path": path,
        "point_count": len(x),
        "bounds": {
            "min": [float(np.min(x)), float(np.min(y)), float(np.min(z))],
            "max": [float(np.max(x)), float(np.max(y)), float(np.max(z))],
        },
        "classification_counts": {
            int(c): int(np.sum(cls == c)) for c in np.unique(cls).tolist()
        },
    }


def build_manifest(write_stats: Dict[str, Any], sample_dir: str) -> Dict[str, Any]:
    hero = HERO_B17
    return {
        "dataset_id": "airoli-s8-hero-lidar",
        "name": "Airoli Sector 8 Hero Case — Raw LiDAR (B-17 Vertical Cadastre)",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "crs": {
            "epsg": 32643,
            "name": "EPSG:32643 — WGS 84 / UTM zone 43N (projected)",
            "local_frame_offset_m": [0.0, 0.0],
            "note": "Local cadastral frame; append UTM 43N easting/northing origin for georeferencing.",
        },
        "sensor": {
            "system": "Synthetic airborne LiDAR (demo) — VLP-like 16-beam scan pattern",
            "accuracy_m": 0.05,
            "point_density_target_pts_m2": 6.0,
        },
        "license": "Open demo data — generated for evaluation; no airborne survey captured.",
        "source_citation": "Bhu-Drishti 3D evaluation dataset (synthetic, deterministic seed 271828).",
        "las_stats": write_stats,
        "ground_truth": {
            "hero_building": hero,
            "fabric_blocks": len(_FABRIC),
            "grove_anchors": len(GROVE_ANCHORS),
        },
    }


def ensure_sample(sample_dir: Optional[str] = None, seed: int = 271828) -> Dict[str, Any]:
    """Generates (if missing) and returns the sample dataset manifest."""
    sample_dir = sample_dir or default_sample_dir()
    os.makedirs(sample_dir, exist_ok=True)
    las_path = os.path.join(sample_dir, "airoli_s8_hero.las")
    meta_path = os.path.join(sample_dir, "metadata.json")
    gt_path = os.path.join(sample_dir, "footprints.geojson")

    if os.path.exists(las_path) and os.path.exists(meta_path):
        with open(meta_path) as f:
            return json.load(f)

    cloud = generate_point_cloud(seed=seed)
    stats = write_las(cloud, las_path)
    manifest = build_manifest(stats, sample_dir)

    ground_truth_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "building_code": HERO_B17["building_code"],
                    "ground_z": HERO_B17["ground_z"],
                    "height_m": 18.0,
                    "levels": len(HERO_B17["levels"]),
                    "basement_depth_m": 3.5,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [HERO_B17["footprint"] + [HERO_B17["footprint"][0]]],
                },
            }
        ],
    }
    for i, (fx0, fy0, fx1, fy1, h) in enumerate(_FABRIC):
        ground_truth_geojson["features"].append({
            "type": "Feature",
            "properties": {"building_code": f"CTX-{i:02d}", "ground_z": 0.0, "height_m": round(h, 1), "levels": 3},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[fx0, fy0], [fx1, fy0], [fx1, fy1], [fx0, fy1], [fx0, fy0]]],
            },
        })

    with open(gt_path, "w") as f:
        json.dump(ground_truth_geojson, f, indent=2)
    with open(meta_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)

    return manifest


def list_datasets(sample_dir: str = DEFAULT_SAMPLE_DIR) -> List[Dict[str, Any]]:
    """Returns discovered real datasets (LAS/LAZ/CSV) plus their manifest if present."""
    out: List[Dict[str, Any]] = []
    if not os.path.isdir(sample_dir):
        return out
    meta_path = os.path.join(sample_dir, "metadata.json")
    manifest: Dict[str, Any] = {}
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            manifest = json.load(f)
    for fname in sorted(os.listdir(sample_dir)):
        if fname.endswith((".las", ".laz", ".csv")):
            out.append({
                "dataset_id": manifest.get("dataset_id", os.path.basename(sample_dir)),
                "name": manifest.get("name", fname),
                "file": fname,
                "path": os.path.join(sample_dir, fname),
                "gt_footprints": os.path.join(sample_dir, "footprints.geojson"),
                "manifest": manifest,
            })
    return out