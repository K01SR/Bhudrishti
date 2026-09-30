"""The one WGS84 <-> EPSG:32643 conversion every cadastral geometry write uses.

`parcels.geom` is declared ``geometry(POLYGON, 32643)``: real projected metres in
UTM zone 43N. Two write paths filled it, and both were wrong:

* ``core.cadastre_store.upsert_parcel`` took whatever the caller passed as
  ``polygon_wkt_2d``. Both live callers built that with ``polygon_wkt(ring)``,
  which *adds the Airoli UTM origin to the ring* -- so an OpenStreetMap or
  GlobalML ring arriving in WGS84 **degrees** was stored as
  ``298000 + lon`` / ``2113500 + lat``. That is not a small offset error: it is
  the difference between easting 298073 and the true easting 289219, about
  8.8 km east, and it collapsed each ring onto a near-point (36 of the 37 stored
  rows have ``ST_Area = 0``). Those are the rows where ``geom`` and the row's own
  ``polygon_geojson`` disagree by ~30 km.
* ``services.builder_records.persist_builder_structure`` did the same with a
  ring the builder drew in the **local metre** frame.

So there are exactly two frames in play, and this module is the only place that
tells them apart:

* :data:`FRAME_WGS84` -- ``[lon, lat]`` degrees, recognised by sitting inside
  India's bounds plus a margin. This is real georeferencing and is what
  ``polygon_geojson`` means by its name.
* :data:`FRAME_LOCAL_METRES` -- metres in a local cadastral frame, recognised by
  NOT sitting in that box. A drawn 24x12 m footprint is 0..24 E / 0..12 N and
  is never confused with degrees.

A third case is refused rather than guessed: a ring that claims to be degrees
but cannot be projected, or one with too few / non-finite vertices, raises
:class:`GeometryRefused`. Nothing here ever produces a 32643 polygon that does
not describe the ring it was given.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

Ring = Sequence[Tuple[float, float]]

#: WGS84 geographic CRS, as every GeoJSON in this codebase means it.
CRS_WGS84 = "EPSG:4326"
#: The projected CRS `parcels.geom`, `structures.geom_3d` and `levels.geom_3d`
#: are all declared in.
CRS_UTM43N = "EPSG:32643"
SRID_UTM43N = 32643

#: Documented Airoli local-frame origin, UTM zone 43N metres. The same numbers
#: appear as ``AIROLI_ORIGIN`` in :mod:`app.core.cadastre_store` and
#: ``AIROLI_DEFAULT`` in :mod:`app.api.v1.ids`; they are the local frame's
#: (0, 0). Placing a local-frame ring here is an *assumption*, recorded as one
#: by :func:`anchor_record`.
AIROLI_ORIGIN = (298000.0, 2113500.0)

# India plus a margin, used only to recognise degrees. Also what lets a metres
# ring through as metres: 24x12 m is nowhere near this box.
INDIA_LON_RANGE = (68.0, 98.0)
INDIA_LAT_RANGE = (6.0, 36.0)

FRAME_WGS84 = "wgs84_degrees"
FRAME_LOCAL_METRES = "local_frame_metres"
FRAME_UNKNOWN = "unknown"

#: What an anchored placement is and is not. Carried into the API response and
#: into ``parcels.provenance_detail`` so no later reader can mistake it for a
#: surveyed position.
ANCHOR_NOTE = (
    "The submitter drew this footprint in the local metre frame, so its "
    "numbers were anchored to the documented Airoli UTM zone 43N origin "
    "(easting 298000.0, northing 2113500.0) to give them a projected "
    "position. That origin is this repository's assumption about its demo "
    "jurisdiction, not a survey: the datum declared for the same precinct in "
    "app/api/v1/osm.py projects 10.3 km away. The position is approximate and "
    "the drawing remains the submitter's claim."
)

_TRANSFORMERS: Dict[Tuple[str, str], Any] = {}


class GeometryRefused(ValueError):
    """Input is not a ring this module is willing to convert.

    Raised instead of returning a plausible-looking 32643 polygon: every
    previous failure of this column was a confidently wrong coordinate.
    """


def _transformer(src: str, dst: str):
    """Cached pyproj transformer. ``always_xy`` means input/output is (lon, lat)."""
    key = (src, dst)
    transformer = _TRANSFORMERS.get(key)
    if transformer is None:
        try:
            from pyproj import Transformer
        except ImportError as exc:  # pragma: no cover - pyproj is a hard requirement
            raise GeometryRefused(
                "pyproj is required to convert between EPSG:4326 and EPSG:32643"
            ) from exc
        transformer = Transformer.from_crs(src, dst, always_xy=True)
        _TRANSFORMERS[key] = transformer
    return transformer


def ring_pairs(ring: Iterable) -> List[Tuple[float, float]]:
    """Coerces a ring to finite (x, y) pairs, or refuses it."""
    try:
        points = [(float(p[0]), float(p[1])) for p in ring]
    except (TypeError, ValueError, IndexError, KeyError) as exc:
        raise GeometryRefused(f"not a ring of coordinate pairs: {exc}") from None
    if len(points) < 3:
        raise GeometryRefused(f"a polygon needs at least 3 vertices, got {len(points)}")
    if not all(math.isfinite(x) and math.isfinite(y) for x, y in points):
        raise GeometryRefused("ring coordinates must be finite numbers")
    return points


def geojson_exterior_ring(polygon: Optional[Dict[str, Any]]) -> List[Tuple[float, float]]:
    """Exterior ring of a GeoJSON Polygon as (lon, lat) pairs, without validating it.

    Returns ``[]`` for anything that is not a ring-shaped object. Whether those
    numbers are *degrees* is a separate question, answered by
    :func:`classify_frame` -- which is the whole point of this module.
    """
    if not isinstance(polygon, dict):
        return []
    coordinates = polygon.get("coordinates")
    if not isinstance(coordinates, (list, tuple)) or not coordinates:
        return []
    exterior = coordinates[0]
    if not isinstance(exterior, (list, tuple)):
        return []
    out: List[Tuple[float, float]] = []
    for point in exterior:
        try:
            out.append((float(point[0]), float(point[1])))
        except (TypeError, ValueError, IndexError, KeyError):
            return []
    return out


def classify_frame(ring: Iterable) -> str:
    """Which frame a ring is in: :data:`FRAME_WGS84`, :data:`FRAME_LOCAL_METRES` or
    :data:`FRAME_UNKNOWN`.

    Magnitude is the discriminator, because that is all a bare ring carries.
    A ring inside India's lon/lat box is degrees; a ring outside it is metres.
    """
    try:
        points = ring_pairs(ring)
    except GeometryRefused:
        return FRAME_UNKNOWN
    if all(INDIA_LON_RANGE[0] <= x <= INDIA_LON_RANGE[1] for x, _ in points) and all(
        INDIA_LAT_RANGE[0] <= y <= INDIA_LAT_RANGE[1] for _, y in points
    ):
        return FRAME_WGS84
    return FRAME_LOCAL_METRES


def is_georeferenced(ring: Iterable) -> bool:
    """True only for a ring of WGS84 degrees inside India's bounds."""
    return classify_frame(ring) == FRAME_WGS84


def geodetic_ring_to_utm43n(ring: Iterable) -> List[Tuple[float, float]]:
    """WGS84 ``[lon, lat]`` ring -> EPSG:32643 ``(easting, northing)`` ring.

    Refuses anything that is not degrees. This is the conversion that was
    missing: adding degrees to a UTM origin is not a projection.
    """
    points = ring_pairs(ring)
    if classify_frame(points) != FRAME_WGS84:
        raise GeometryRefused(
            "ring is not georeferenced degrees, so it will not be projected; "
            "local-frame metres need an explicit anchor"
        )
    eastings, northings = _transformer(CRS_WGS84, CRS_UTM43N).transform(
        [x for x, _ in points], [y for _, y in points]
    )
    return [(float(e), float(n)) for e, n in zip(eastings, northings)]


def utm43n_ring_to_wgs84(ring: Iterable) -> List[Tuple[float, float]]:
    """EPSG:32643 ``(easting, northing)`` ring -> WGS84 ``(lon, lat)`` ring."""
    points = ring_pairs(ring)
    lons, lats = _transformer(CRS_UTM43N, CRS_WGS84).transform(
        [x for x, _ in points], [y for _, y in points]
    )
    return [(float(lon), float(lat)) for lon, lat in zip(lons, lats)]


def anchor_local_ring(
    ring_m: Iterable, origin: Tuple[float, float] = AIROLI_ORIGIN
) -> List[Tuple[float, float]]:
    """Local-frame metre ring -> EPSG:32643 ring by adding a declared origin.

    This is an assumption, not a measurement. See :data:`ANCHOR_NOTE` and
    :func:`anchor_record`.
    """
    points = ring_pairs(ring_m)
    return [(origin[0] + x, origin[1] + y) for x, y in points]


def utm43n_polygon_ewkt(ring_utm: Iterable) -> str:
    """EWKT ``POLYGON`` in EPSG:32643 from an already-projected ring."""
    points = ring_pairs(ring_utm)
    parts = [f"{x:.3f} {y:.3f}" for x, y in points]
    if parts[0] != parts[-1]:
        parts.append(parts[0])
    # A WKT POLYGON needs its own inner ring parentheses: POLYGON((x y, ...)).
    # Emitting POLYGON(x y, ...) makes PostGIS fail with "parse error - invalid
    # geometry" at the first coordinate, which surfaces as a failed insert on
    # every parcel write rather than as an obvious format error.
    return f"SRID={SRID_UTM43N};POLYGON(({', '.join(parts)}))"


def geodetic_polygon_ewkt(ring: Iterable) -> Optional[str]:
    """EWKT for a WGS84 ring, or ``None`` when the ring is not in degrees.

    ``None`` means "this polygon is not georeferenced", which is a fact the
    caller has to record -- never a silent fallback to some other frame.
    """
    if classify_frame(ring) != FRAME_WGS84:
        return None
    try:
        return utm43n_polygon_ewkt(geodetic_ring_to_utm43n(ring))
    except GeometryRefused:
        return None


def anchored_polygon_ewkt(
    ring_m: Iterable, origin: Tuple[float, float] = AIROLI_ORIGIN
) -> str:
    """EWKT for a local-frame metre ring, placed at a declared origin."""
    return utm43n_polygon_ewkt(anchor_local_ring(ring_m, origin))


def polygon_ewkt(
    ring: Iterable,
    *,
    frame: Optional[str] = None,
    origin: Tuple[float, float] = AIROLI_ORIGIN,
) -> str:
    """EWKT in EPSG:32643 for either frame.

    ``frame`` should be passed whenever the caller already knows which one it
    has; detection by magnitude is a fallback, not a guarantee.
    """
    resolved = frame or classify_frame(ring)
    if resolved == FRAME_WGS84:
        return utm43n_polygon_ewkt(geodetic_ring_to_utm43n(ring))
    if resolved == FRAME_LOCAL_METRES:
        return anchored_polygon_ewkt(ring, origin)
    raise GeometryRefused(f"cannot classify ring frame (got {resolved!r})")


def anchor_record(origin: Tuple[float, float] = AIROLI_ORIGIN) -> Dict[str, Any]:
    """The fact an anchored placement has to travel with the row.

    Stored in ``parcels.provenance_detail`` so any later reader of the geometry
    -- including the identifier derivation on acceptance -- can say that the
    position is assumed.
    """
    return {
        "geometry_frame": FRAME_LOCAL_METRES,
        "georeferenced": False,
        "anchor_origin": {"easting": origin[0], "northing": origin[1], "srid": SRID_UTM43N},
        "anchor_basis": "documented-demo-jurisdiction-origin",
        "anchor_note": ANCHOR_NOTE,
    }