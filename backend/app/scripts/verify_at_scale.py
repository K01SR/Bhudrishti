"""verify_at_scale: nationwide integrity audit + endpoint load checks.

Phase 7 verification of the national cadastral stack. Run inside the backend
container:

    docker exec bhudrishti_backend python3 -m app.scripts.verify_at_scale

Checks:
1. Boundary integrity  - admin_boundaries hierarchy (parents exist, orphans, level mix)
2. Parcel integrity    - every stored parcel RE-DERIVES its ULPIN from its own
                         stored geometry (engine-first source of truth), geometry
                         validity, area sanity
3. Twin integrity      - every twin maps to a real parcel; FSI/height sanity;
                         geo-referenced 4326 footprint validity
4. Load/response check - tiles + viz + locations endpoints over HTTP, latency
"""

from __future__ import annotations

import time
from typing import Dict

from sqlalchemy import text

from app.core.database import sync_engine, SyncSessionLocal
from app.id_engine.national import verify_parcel_ulpin


def audit_boundaries(report: Dict[str, object]) -> None:
    with sync_engine.connect() as c:
        subset = c.execute(text(
            "SELECT count(*) FROM admin_boundaries WHERE code IN "
            "('MH-AHMADNAGAR','JH-SAHIBGANJ','JH-SAHIBGANJ-T-02','JH-SAHIBGANJ-T-02-V-03')"
        )).scalar()
        report["boundaries"] = {
            "total": c.execute(text("SELECT count(*) FROM admin_boundaries")).scalar(),
            "by_level": dict(c.execute(text(
                "SELECT level, count(*) FROM admin_boundaries GROUP BY level"
            )).all()),
            "orphan_rows": c.execute(text(
                "SELECT count(*) FROM admin_boundaries a WHERE a.parent_code IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM admin_boundaries p WHERE p.code = a.parent_code)"
            )).scalar(),
            "seeded_boundaries_present": subset,
        }


def audit_parcels(report: Dict[str, object]) -> None:
    with SyncSessionLocal() as db:
        parcels = db.execute(text(
            "SELECT ulpin, ST_IsValid(geom) AS valid, area_m2 FROM national_parcels"
        )).all()
        total = len(parcels)
        invalid_geo = sum(1 for p in parcels if not p.valid)
        missing_area = sum(1 for p in parcels if p.area_m2 is None or p.area_m2 <= 0)

        geom_rows = db.execute(
            text("SELECT ulpin, geom FROM national_parcels")
        ).all()
        from shapely import wkb, wkt
        parsed = []
        for u, g in geom_rows:
            geom = None
            if isinstance(g, bytes):
                geom = wkb.loads(g)
            elif isinstance(g, str):
                if g.startswith(tuple("0123456789ABCDEF")):
                    try:
                        geom = wkb.loads(g, hex=True)
                    except Exception:  # noqa: BLE001
                        geom = wkt.loads(g)
                else:
                    geom = wkt.loads(g)
            parsed.append((u, geom))

        verified = 0
        mismatches: list[str] = []
        for u, shp in parsed:
            if shp is None or not hasattr(shp, "exterior"):
                mismatches.append(u)
                continue
            ring = [(round(float(y), 6), round(float(x), 6)) for x, y in shp.exterior.coords[:-1]]
            ok, _ = verify_parcel_ulpin(u, ring)
            if ok:
                verified += 1
            else:
                mismatches.append(u)

    report["parcels"] = {
        "total": total,
        "invalid_geometry": invalid_geo,
        "missing_area": missing_area,
        "ulpin_rederived_from_stored_geometry": verified,
        "mismatches": mismatches[:10],
        "mismatch_count": total - verified,
    }


def audit_twins(report: Dict[str, object]) -> None:
    with sync_engine.connect() as c:
        rows = c.execute(text(
            "SELECT count(*) AS total, "
            "count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM national_parcels p "
            "  WHERE p.ulpin = national_twins.ulpin)) AS orphan, "
            "count(*) FILTER (WHERE fsi < 0 OR height_m <= 0) AS bad_metric, "
            "count(*) FILTER (WHERE footprint_area_m2 IS NULL OR footprint_area_m2 < 0) AS bad_fp, "
            "count(*) FILTER (WHERE ST_IsValid(footprint_polygon) = FALSE) AS bad_footprint "
            "FROM national_twins"
        )).one()
    report["twins"] = {
        "total": rows.total,
        "orphan_twins": rows.orphan,
        "bad_fsi_or_height": rows.bad_metric,
        "bad_footprint_area": rows.bad_fp,
        "invalid_footprint_geometry": rows.bad_footprint,
    }


def load_checks(report: Dict[str, object]) -> None:
    import urllib.request

    base = "http://localhost:8000/api/v1"
    urls = [
        "/viz/fsi/DISTRICT",
        "/viz/density/STATE",
        "/viz/status/DISTRICT",
        "/tiles/6/45/27.pbf?layers=state,district",
        "/tiles/12/3046/1755.pbf?layers=village,parcel,twin",
        "/locations/states",
    ]
    results = []
    for path in urls:
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(f"{base}{path}", timeout=20) as r:
                body = r.read()
            dt_ms = (time.perf_counter() - t0) * 1000
            results.append({
                "path": path,
                "status": r.status,
                "bytes": len(body),
                "ms": round(dt_ms, 1),
            })
        except Exception as exc:  # noqa: BLE001
            results.append({"path": path, "error": str(exc)})
    report["load"] = results


async def main() -> None:
    report: Dict[str, object] = {}
    audit_boundaries(report)
    audit_parcels(report)
    audit_twins(report)
    load_checks(report)

    import json
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())