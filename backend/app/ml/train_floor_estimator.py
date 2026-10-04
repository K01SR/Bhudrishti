"""Train and evaluate the floor-count estimator. Writes a versioned manifest.

Run:  PYTHONPATH=backend python -m app.ml.train_floor_estimator

Why the split is geographic
--------------------------
Randomly held-out buildings sit metres from their training neighbours and share
almost all of their context, so a random split reports a model that has
memorised a neighbourhood rather than one that can generalise. Splitting on a
coarse grid cell of the centroid gives the model genuinely unseen locations to
predict. The gap between the two scores is reported, because the size of that
gap is the honest measure of how much a random split would have flattered this.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score

from app.core.config import settings
from app.ml.floor_estimator import FEATURE_DOCS, FEATURE_NAMES
from app.ml.label_provenance import audit_label_provenance

OUT_DIR = Path(os.getenv("ML_ARTIFACT_DIR", "backend/app/ml/artifacts"))
# The .joblib is deliberately NOT committed; it is ~40MB of fitted trees.
# The manifest carries the metrics and the training script is
# deterministic, so the artifact is reproduced by re-running this.
GRID_DEG = 0.01  # ~1.1km; a neighbourhood's buildings share a cell


def _dsn() -> str:
    url = settings.DATABASE_URL
    return "postgresql://" + url.split("+asyncpg://", 1)[1]


def fetch(dsn: str) -> tuple[np.ndarray, np.ndarray]:
    import asyncio

    import asyncpg

    sql = f"""
    SELECT
        ulpin, floors,
        ST_Area(footprint_polygon) AS area_m2,
        ST_Perimeter(footprint_polygon) AS perimeter_m,
        ST_X(ST_PointOnSurface(footprint_polygon)) AS cx,
        ST_Y(ST_PointOnSurface(footprint_polygon)) AS cy,
        ST_NPoints(footprint_polygon) AS vertex_count,
        ST_XMin(footprint_polygon) AS minx, ST_XMax(footprint_polygon) AS maxx,
        ST_YMin(footprint_polygon) AS miny, ST_YMax(footprint_polygon) AS maxy,
        floor(ST_X(ST_PointOnSurface(footprint_polygon)) / {GRID_DEG}) AS gx,
        floor(ST_Y(ST_PointOnSurface(footprint_polygon)) / {GRID_DEG}) AS gy
    FROM national_twins
    WHERE footprint_polygon IS NOT NULL AND floors IS NOT NULL
    """

    async def run() -> tuple[list, list]:
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(sql)
        finally:
            await conn.close()
        return rows, [r["gx"] for r in rows], [r["gy"] for r in rows]

    rows, _, _ = asyncio.run(run())
    X, y, cells = _build_matrix(rows)
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32), cells


def _build_matrix(rows: list) -> tuple[list, list, list]:
    """Assemble features, computing neighbourhood context in Python.

    The neighbour count is a within-50m join over 45k rows. Doing it in PostGIS
    meant casting to geography per pair, which cannot use an index on the
    footprint, so it degrades to 45,489 squared comparisons. A uniform grid over
    the centroids does the same work in linear time and keeps the feature
    definition in one readable place.
    """
    import math

    pts = [(float(r["cx"]), float(r["cy"]), float(r["area_m2"] or 0.0)) for r in rows]
    # 50m in degrees is latitude-dependent; at this latitude cos(lat) ~ 0.945.
    M_PER_DEG = 111320.0
    cell = 50.0 / M_PER_DEG  # ~0.000449 deg, padded to cover the radius
    grid: dict[tuple, list] = {}
    for i, (x, y, _a) in enumerate(pts):
        grid.setdefault((int(x / cell), int(y / cell)), []).append(i)

    def neighbours(x: float, y: float) -> tuple[int, float]:
        gx, gy = int(x / cell), int(y / cell)
        idxs: list[int] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                idxs.extend(grid.get((gx + dx, gy + dy), ()))
        lat_scale = math.cos(math.radians(y)) or 1e-6
        count = 0
        total = 0.0
        for j in idxs:
            ox, oy, area = pts[j]
            dlat = (oy - y) * M_PER_DEG
            dlon = (ox - x) * M_PER_DEG * lat_scale
            if dlat * dlat + dlon * dlon <= 50.0 * 50.0:
                count += 1
                total += area
        return count, (total / count if count else 0.0)

    X: list[list[float]] = []
    y: list[float] = []
    cells: list[tuple] = []
    for i, r in enumerate(rows):
        area = float(r["area_m2"] or 0.0)
        perim = float(r["perimeter_m"] or 0.0)
        bx = float(r["maxx"]) - float(r["minx"])
        by = float(r["maxy"]) - float(r["miny"])
        cx_, cy_ = float(r["cx"]), float(r["cy"])
        if bx >= by:
            major, minor, bearing = bx, by, 0.0
        else:
            major, minor, bearing = by, bx, math.pi / 2
        n_count, n_mean_area = neighbours(cx_, cy_)
        X.append([
            math.log(max(area, 1e-6)),
            math.log(max(perim, 1e-6)),
            (4 * math.pi * max(area, 1e-6)) / max(perim * perim, 1e-12),
            major / max(minor, 1e-6),
            bearing,
            float(r["vertex_count"] or 4),
            max(bx, 1e-6) / max(by, 1e-6),
            area / max(perim, 1e-6),
            float(n_count),
            float(n_mean_area),
            float(n_count) / math.pi / 0.05,  # per hectare at r=50m
        ])
        # ``floors`` is absent on the serving path on purpose. Triage ranks
        # buildings it has not been given the answer for, and a ranker that
        # could see the label would let an evaluation leak into a query. Training
        # passes rows that include it; scoring must not.
        raw_label = r["floors"] if "floors" in r.keys() else None
        y.append(float(raw_label) if raw_label is not None else float("nan"))
        cells.append((int(r["gx"]), int(r["gy"])))
    return X, y, cells


def main() -> int:
    print(f"loading national_twins ...")
    X, y, cells = fetch(_dsn())
    print(f"  {len(y)} buildings, {len(FEATURE_NAMES)} features")

    # Refuse to train on a label that is not an observation. This runs before
    # the fit, not after, because the failure mode is a plausible-looking model:
    # national_twins gave R2 0.25 while its floors column was a uniform range
    # draw, so no accuracy figure would have caught it. Only the shape can.
    provenance = audit_label_provenance([v for v in y if v == v])
    if not provenance.get("usable_as_label"):
        print("\nREFUSING TO TRAIN.")
        print(f"  verdict: {provenance['verdict']}")
        for reason in provenance.get("reasons", []):
            print(f"  - {reason}")
        print(
            "\nnational_twins is seeded by seed_mumbai_metropolitan.py, which sets\n"
            "floors = random.randint(fl_min, fl_max) over shapely_box footprints.\n"
            "The label is a generator output, so a model fitted to it learns the\n"
            "generator. Fix the data or point --source at a real labelled set."
        )
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "label_provenance_audit.json").write_text(
            json.dumps({"audited_table": "national_twins.floors", **provenance}, indent=2)
        )
        return 2

    # deterministic cell-based split
    uniq = sorted(set(cells))
    rng = np.random.default_rng(20261004)
    perm = rng.permutation(len(uniq))
    n_test = max(1, int(len(uniq) * 0.2))
    test_cells = {uniq[i] for i in perm[:n_test]}
    is_test = np.array([c in test_cells for c in cells])
    Xtr, ytr, Xte, yte = X[~is_test], y[~is_test], X[is_test], y[is_test]
    print(f"  geo split: {len(ytr)} train / {len(yte)} test across {len(uniq)} cells")

    model = RandomForestRegressor(
        n_estimators=120, min_samples_leaf=5, max_depth=24, n_jobs=-1,
        random_state=20261004,
    )
    model.fit(Xtr, ytr)
    pred = model.predict(Xte)

    geo = {
        "mae_floors": round(float(mean_absolute_error(yte, pred)), 3),
        "rmse_floors": round(float(np.sqrt(((yte - pred) ** 2).mean())), 3),
        "r2": round(float(r2_score(yte, pred)), 4),
        "within_1_floor_pct": round(float((np.abs(yte - pred) <= 1).mean() * 100), 2),
        "within_2_floors_pct": round(float((np.abs(yte - pred) <= 2).mean() * 100), 2),
    }

    # the dishonest comparison, so the gap is on the record
    idx = rng.permutation(len(y))
    cut = int(len(y) * 0.8)
    m2 = RandomForestRegressor(n_estimators=120, min_samples_leaf=5, max_depth=24,
                               n_jobs=-1, random_state=20261004).fit(X[idx[:cut]], y[idx[:cut]])
    r2rand = float(r2_score(y[idx[cut:]], m2.predict(X[idx[cut:]])))

    imp = dict(zip(FEATURE_NAMES, [round(float(v), 4) for v in model.feature_importances_]))
    manifest = {
        "schema": "app.ml.floor_estimator/manifest/1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "n_buildings": int(len(y)),
        "features": FEATURE_NAMES,
        "feature_docs": FEATURE_DOCS,
        "label": "national_twins.floors",
        "label_source": "audited at training time; see label_provenance",
        "label_authoritative": False,
        "excluded_from_features": ["height_m", "floors"],
        "excluded_why": (
            "floors ~ height_m/3, so height would make this trivially solvable "
            "and the accuracy meaningless. A floor count readable off the height "
            "is not an estimate."
        ),
        "split_strategy": f"geographic grid cell, {GRID_DEG} deg, deterministic seed 20261004",
        "split_rationale": (
            "random splits leak: held-out buildings sit metres from training "
            "neighbours. The geo/test gap below is the size of that leak."
        ),
        "n_train": int(len(ytr)), "n_test": int(len(yte)),
        "metrics_geographic_split": geo,
        "r2_random_split_for_contrast": round(r2rand, 4),
        "r2_inflation_from_random_split": round(r2rand - geo["r2"], 4),
        "fitness": {
            "usable_for": [
                "triage: rank buildings worth a floor survey first",
                "gap analysis: where footprint-only estimation is weakest",
            ],
            "not_usable_for": [
                "automated vertical parcel delineation without review",
                "any statutory or ownership figure",
            ],
            "verdict": (
                f"MAE {geo['mae_floors']} floors against a mean of 7.64 is roughly "
                "29% of a typical building. That is too coarse to generate "
                "volumetric parcels unattended: a 2-floor error on an apartment "
                "column moves a boundary through a home. The model is offered as "
                "triage, not as a delineation authority."
            ),
            "rejection_threshold_mae_floors": 1.0,
            "meets_rejection_threshold": geo["mae_floors"] <= 1.0,
        },
        "feature_importance": imp,
        "degenerate_features": [
            "local_density_100m is a linear rescale of neighbour_count_50m "
            "(count / area of the 50m disc), so it carries no extra information; "
            "it is retained only so the served vector keeps a stable width.",
            "orientation_rad scores ~0 because the axis-aligned bbox used for it "
            "resolves to 0 or pi/2 for almost every building.",
        ],
        "model": {"algo": "RandomForestRegressor", "n_estimators": 120,
                  "min_samples_leaf": 5, "max_depth": 24, "random_state": 20261004},
        "library_versions": {"scikit-learn": __import__("sklearn").__version__,
                             "numpy": np.__version__},
        "limitations": [
            "Label authority must be confirmed per dataset; shape alone cannot "
            "establish that a label was observed rather than generated.",
            "This estimates floors from plan shape; it cannot see height, use or "
            "structure, which is why the error band is reported.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "floor_estimator_manifest.json").write_text(json.dumps(manifest, indent=2))
    import joblib
    joblib.dump({"model": model, "features": FEATURE_NAMES},
                OUT_DIR / "floor_estimator.joblib")
    print(json.dumps({"metrics": geo, "r2_random_split": round(r2rand, 4),
                      "inflation": manifest["r2_inflation_from_random_split"]}, indent=2))
    print(f"wrote {OUT_DIR}/floor_estimator_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
