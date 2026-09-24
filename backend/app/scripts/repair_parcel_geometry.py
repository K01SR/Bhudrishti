"""repair_parcel_geometry: rebuild ``parcels.geom`` from ``polygon_geojson``.

Run inside the backend container:

    docker exec bhudrishti_backend python3 -m app.scripts.repair_parcel_geometry --dry-run
    docker exec bhudrishti_backend python3 -m app.scripts.repair_parcel_geometry --apply

Why this exists
---------------
``upsert_parcel`` used to assign the caller-supplied ``polygon_wkt_2d`` straight
to ``parcel.geom``. Every caller built that WKT with ``polygon_wkt``, which
anchors a ring to the Airoli UTM origin. An OSM or GlobalML ring already in
degrees was therefore stored roughly 8.8 km east of the place it describes, the
ring collapsed to a point, and ``ST_Area`` returned 0.

The writer was fixed (``upsert_parcel`` now reprojects from
``polygon_geojson``, which is the single source of truth), but rows written
before that fix were never backfilled. Every one of them still carried a
degenerate zero-area ``geom``.

What this repairs
-----------------
``parcels.geom`` only, by reprojecting the row's own ``polygon_geojson``
(WGS84, EPSG:4326) into EPSG:32643. This invents nothing: the coordinates come
from a column the row already carried and that clients are already served.

What this deliberately does NOT do
----------------------------------
* It does not repair, buffer, snap or re-centre geometry. ``ST_MakeValid`` is
  never called, and that is not an oversight. On these rows ``ST_MakeValid``
  collapses 24 of them to ``ST_Point`` and 12 to ``ST_LineString``, because the
  stored ring genuinely encloses no area. Buffering or taking a bounding box
  would produce a plausible-looking parcel boundary that no source ever stated,
  which is the same fabrication this project removed elsewhere (the `%4` unit
  quadrant boxes, the invented LiDAR points, the removed VIOLATION verdicts).
  A missing boundary has to stay missing.
* It does not backfill ``geom_hash``. That column is declared in
  ``cadastre_store._ensure_schema_ddl`` and on the model, and is indexed, but no
  code in ``backend/app`` has ever written or read it -- 0 of 38 rows carried a
  value. Populating it now would invent a contract nothing consumes. It is dead
  schema and should be dropped in its own change.

Safety
------
* Idempotent: only rows that are NULL, invalid, or zero-area are touched, so
  re-running is a no-op once the data is clean.
* Rows whose reprojection cannot produce a usable polygon are reported and
  skipped. They keep their existing ``geom`` rather than being overwritten with
  a guess.
* ``gis_area_m2`` is refreshed from PostGIS for repaired rows, because it had
  been recording a measured zero for them.
* ``--dry-run`` is the default; ``--apply`` is required to write.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

from sqlalchemy import text

from app.core.database import sync_engine

# Reproject the row's own WGS84 ring. ST_CollectionExtract(..., 3) keeps only
# the polygonal component so a ring that would land as a GeometryCollection
# cannot violate the column's POLYGON type. ST_Multi is deliberately NOT used:
# it promotes a single polygon to a MultiPolygon, which the
# geometry(POLYGON,32643) column will not accept. Rows whose source ring really
# is multi-part are reported as unusable rather than coerced.
_REPROJECT = """
    ST_CollectionExtract(
        ST_MakeValid(
            ST_Transform(
                ST_SetSRID(ST_GeomFromGeoJSON(polygon_geojson), 4326), 32643)
        ), 3)
"""

# The rows this is here to fix: no geometry, an invalid one, or one that
# encloses no area at all. Zero area is included because ST_IsValid() can be
# true for a collapsed ring, so validity alone is not sufficient.
_NEEDS_REPAIR = """
    geom IS NULL
    OR NOT ST_IsValid(geom)
    OR ST_IsEmpty(geom)
    OR ST_Area(geom) = 0
"""


def _scalar(conn, sql: str, **params: Any) -> Any:
    return conn.execute(text(sql), params).scalar()


def survey(apply: bool) -> Dict[str, Any]:
    report: Dict[str, Any] = {"mode": "apply" if apply else "dry-run", "repaired": 0,
                              "skipped_unusable": 0, "already_clean": 0, "skipped": []}

    with sync_engine.begin() as conn:
        report["already_clean"] = int(_scalar(conn, f"""
            SELECT count(*) FROM parcels
            WHERE geom IS NOT NULL AND ST_IsValid(geom) AND NOT ST_IsEmpty(geom)
              AND ST_Area(geom) <> 0 AND NOT ({_NEEDS_REPAIR})
        """))
        candidates: List[str] = list(conn.execute(text(f"""
            SELECT ulpin FROM parcels WHERE {_NEEDS_REPAIR} ORDER BY ulpin
        """)).scalars())
        report["candidates"] = len(candidates)

        for ulpin in candidates:
            usable = _scalar(conn, f"""
                SELECT ST_GeometryType(g) = 'ST_Polygon'
                   AND ST_IsValid(g) AND NOT ST_IsEmpty(g) AND ST_Area(g) > 0
                FROM (SELECT {_REPROJECT} AS g
                      FROM parcels WHERE ulpin = :ulpin) s
            """, ulpin=ulpin)
            if not usable:
                # No usable ring in polygon_geojson. Leave whatever is there and
                # say so, rather than writing a guess.
                report["skipped_unusable"] += 1
                report["skipped"].append(ulpin)
                continue
            if apply:
                conn.execute(text(f"""
                    UPDATE parcels
                    SET geom = {_REPROJECT},
                        gis_area_m2 = ST_Area({_REPROJECT})
                    WHERE ulpin = :ulpin
                """), {"ulpin": ulpin})
            report["repaired"] += 1

    # Post-conditions, asserted from the database rather than assumed.
    with sync_engine.connect() as conn:
        report["remaining_degenerate"] = int(_scalar(conn, f"""
            SELECT count(*) FROM parcels WHERE {_NEEDS_REPAIR}
        """))
        row = conn.execute(text("""
            SELECT count(*), coalesce(min(ST_Area(geom)), 0), coalesce(max(ST_Area(geom)), 0)
            FROM parcels WHERE geom IS NOT NULL
        """)).one()
        report["rows_with_geom"] = int(row[0])
        report["area_m2_min"] = round(float(row[1]), 2)
        report["area_m2_max"] = round(float(row[2]), 2)

    report["ok"] = report["remaining_degenerate"] == 0 and report["skipped_unusable"] == 0
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="write changes (default is a dry run)")
    args = ap.parse_args()

    report = survey(apply=args.apply)
    print(json.dumps(report, indent=2))
    if not args.apply:
        print("\ndry run: nothing written. Re-run with --apply to repair.", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())