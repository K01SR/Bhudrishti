"""parcels.geom must never be NULL, invalid, or enclose zero area.

Background
----------
``upsert_parcel`` used to assign the caller-supplied ``polygon_wkt_2d`` straight
to ``parcel.geom``. Callers built that WKT with ``polygon_wkt``, which anchors a
ring to the Airoli UTM origin, so an OSM or GlobalML ring already in degrees was
stored ~8.8 km east of the place it described. The ring collapsed to a point and
``ST_Area`` returned 0 for 37 parcels, while ``gis_area_m2`` recorded a measured
zero.

The writer was fixed to reproject from ``polygon_geojson``, but the rows written
before that fix were never backfilled. ``app.scripts.repair_parcel_geometry``
does the backfill; these tests assert the invariant it establishes, so a future
ingestion path cannot quietly reintroduce collapsed geometry.

The distinction that matters: the *source* coordinates in ``polygon_geojson``
were always intact. It was only the stored PostGIS copy that was degenerate, so
this is a repair, not a fabrication. Nothing here invents a boundary, and the
repair script refuses to buffer or bounding-box a ring that has no area.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.database import sync_engine


def _scalar(sql: str):
    with sync_engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


@pytest.fixture(scope="module")
def geometry_stats():
    with sync_engine.connect() as conn:
        return conn.execute(text("""
            SELECT
                count(*) FILTER (WHERE geom IS NULL)                        AS null_geom,
                count(*) FILTER (WHERE geom IS NOT NULL
                                   AND NOT ST_IsValid(geom))              AS invalid_geom,
                count(*) FILTER (WHERE geom IS NOT NULL
                                   AND ST_IsEmpty(geom))                   AS empty_geom,
                count(*) FILTER (WHERE geom IS NOT NULL
                                   AND ST_Area(geom) = 0)                 AS zero_area_geom,
                count(*)                                                AS total
            FROM parcels
        """)).mappings().one()


def test_no_parcel_has_a_null_geom(geometry_stats):
    # NULL is survivable -- it honestly means "no boundary" -- but it must be
    # rare and deliberate, not the default result of ingestion.
    assert geometry_stats["null_geom"] == 0, (
        f"{geometry_stats['null_geom']} parcel(s) have geom IS NULL; run "
        f"python3 -m app.scripts.repair_parcel_geometry --apply"
    )


def test_no_stored_geom_is_topologically_invalid(geometry_stats):
    assert geometry_stats["invalid_geom"] == 0, (
        f"{geometry_stats['invalid_geom']} parcel(s) hold a self-intersecting or "
        f"otherwise invalid geometry"
    )


def test_no_stored_geom_is_empty_or_zero_area(geometry_stats):
    # This is the assertion that would have caught the original bug. A ring
    # anchored to the wrong origin collapses to a point: ST_IsValid can still be
    # true, so validity alone is not enough -- the area has to be checked too.
    assert geometry_stats["zero_area_geom"] == 0, (
        f"{geometry_stats['zero_area_geom']} parcel(s) enclose zero area, which "
        f"means the ring was projected from the wrong origin"
    )
    assert geometry_stats["empty_geom"] == 0


def test_stored_geom_agrees_with_its_own_polygon_geojson():
    """The stored PostGIS copy must be the reprojection of polygon_geojson.

    ``polygon_geojson`` (EPSG:4326) is what clients are served, so it is the
    source of truth. ``geom`` (EPSG:32643) is a derived convenience copy for
    spatial predicates and ST_Area. If the two ever diverge, area and
    containment queries answer from a different shape than the map draws.
    """
    mismatched = _scalar("""
        SELECT count(*) FROM parcels
        WHERE geom IS NOT NULL
          AND polygon_geojson IS NOT NULL
          AND ST_AsText(geom) IS DISTINCT FROM
              ST_AsText(
                ST_CollectionExtract(
                  ST_MakeValid(
                    ST_Transform(
                      ST_SetSRID(ST_GeomFromGeoJSON(polygon_geojson), 4326), 32643)
                  ), 3))
    """)
    assert mismatched == 0, (
        f"{mismatched} parcel(s) have a geom that is not the reprojection of their "
        f"own polygon_geojson; clients are served the latter"
    )


def test_gis_area_is_populated_and_plausible():
    """gis_area_m2 must be a real measurement, not the zero the bug recorded."""
    with sync_engine.connect() as conn:
        row = conn.execute(text("""
            SELECT count(*) FILTER (WHERE geom IS NOT NULL
                                     AND (gis_area_m2 IS NULL OR gis_area_m2 <= 0)) AS bad,
                   count(*) FILTER (WHERE geom IS NOT NULL)                        AS with_geom,
                   coalesce(min(gis_area_m2) FILTER (WHERE gis_area_m2 > 0), 0)      AS smallest
            FROM parcels
        """)).mappings().one()
    assert row["bad"] == 0, f"{row['bad']} parcel(s) have a missing or non-positive gis_area_m2"
    if row["with_geom"]:
        # A sub-square-metre "parcel" is the signature of the collapsed ring.
        assert row["smallest"] > 1.0, (
            f"smallest gis_area_m2 is {row['smallest']}, which indicates collapsed "
            f"geometry rather than a real boundary"
        )