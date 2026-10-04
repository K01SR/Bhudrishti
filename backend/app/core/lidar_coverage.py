"""Where open airborne LiDAR actually exists.

This module exists to stop the question being re-researched, and to let the API
answer it honestly instead of shrugging. The point-cloud endpoints used to
refuse with one reason - the demo gate - which left a caller unable to tell
"this deployment is not serving generated data" apart from "no such data is
published for this place at all". Those are different facts and only one of them
is fixable by turning an environment variable.

Verified 2026-09 by auditing the public, credential-free sources:

- ``open-lidar-data`` (public S3 bucket, ``s3://open-lidar-data``) aggregates
  national LiDAR for ``BE CH DE DK EE ES FI FR IE LU LV NL PL SE SI UK US``.
  India is absent. It serves COPC, which is range-readable and therefore
  streamable.
- ``s3://usgs-lidar-public`` serves USGS 3DEP as Entwine Point Tiles, also
  streamable, and ``s3://usgs-lidar-requester-pays`` as raw LAZ. United States
  only.
- ``tnmaccess.nationalmap.gov`` needs no credentials but is likewise US-only.
- ISRO/NRSC Bhuvan publishes satellite imagery, orthoimagery, thematic services
  and DEMs. It does not publish airborne LiDAR point clouds; the Open Data
  Archive is login-gated and carries no LAZ product.

So there is no open airborne LiDAR for India, and therefore none for any of the
precincts this product serves (Airoli, Bandra West, Delhi, Mumbai Fort,
Bengaluru). LAZ decoding is not the obstacle - ``laspy`` is already a dependency
and the ``lazrs`` backend installs cleanly - coverage is.

What this deployment does serve instead, and must not call LiDAR:

- building footprints from Microsoft GlobalML or OpenStreetMap;
- ground and surface elevation from AWS Terrain Tiles (terrarium), a real
  global elevation raster;
- a modelled point field in :func:`app.opendata.service.area_lidar_points`,
  labelled ``MODELLED``.

The honest consequence is that the LiDAR view is unavailable for these areas by
construction, not by outage. Callers get told so, with the reason.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

#: Country codes with verified open airborne LiDAR, and the source that has it.
#: Deliberately conservative: a country is listed only when a credential-free
#: bucket was confirmed to serve it, because a source that needs an account is
#: not something an unauthenticated deployment can fall back on.
OPEN_LIDAR_COVERAGE: Dict[str, Dict[str, str]] = {
    code: {"bucket": "open-lidar-data", "region": "eu-central-1", "format": "COPC/LAZ"}
    for code in ("BE", "CH", "DE", "DK", "EE", "ES", "FI", "FR", "IE", "LU", "LV", "NL", "PL", "SE", "SI", "UK")
}
OPEN_LIDAR_COVERAGE["US"] = {
    "bucket": "usgs-lidar-public",
    "region": "us-west-2",
    "format": "EPT (Entwine Point Tiles, LAZ)",
}

#: Coarse boxes for the sources above, as (lat_min, lat_max, lon_min, lon_max).
#: Enough to answer "is there any chance this area has open LiDAR", which is the
#: only question the endpoints ask. Not a substitute for a real tile index.
_COVERAGE_BOXES: List[Tuple[float, float, float, float]] = [
    (49.0, 51.5, 5.5, 6.5),    # BE
    (45.8, 47.8, 5.9, 10.5),   # CH
    (47.2, 55.1, 5.8, 15.1),   # DE
    (54.5, 57.8, 8.0, 15.2),   # DK
    (57.5, 59.7, 21.7, 28.2),  # EE
    (35.9, 43.9, -9.3, 3.3),   # ES
    (59.7, 70.1, 19.5, 31.6),  # FI
    (41.3, 51.2, -5.2, 9.6),   # FR
    (51.4, 55.4, -10.6, -5.9), # IE
    (49.4, 50.2, 5.7, 6.6),    # LU
    (55.6, 58.1, 21.0, 28.3),  # LV
    (50.7, 53.6, 3.3, 7.3),    # NL
    (49.0, 54.9, 14.1, 24.2),  # PL
    (55.3, 69.1, 11.0, 24.2),  # SE
    (45.4, 46.9, 13.3, 16.6),  # SI
    (49.8, 61.0, -8.7, 1.8),   # UK
    (18.0, 71.5, -179.0, -66.0),  # US, lower 48 + AK + HI
]

NO_COVERAGE_MESSAGE = (
    "No open airborne LiDAR exists for this area. The credential-free public "
    "LiDAR archives (open-lidar-data, USGS 3DEP ETP) cover Europe and the "
    "United States only; ISRO/NRSC Bhuvan publishes imagery and DEMs but no "
    "point clouds, so India has no open LiDAR coverage. This is a property of "
    "the available data, not an outage, and no environment variable changes it. "
    "Building footprints (Microsoft GlobalML, OpenStreetMap) and elevation "
    "(AWS Terrain Tiles) are available for this area and are what the 3D view "
    "renders."
)


def open_lidar_coverage(lat: float, lon: float) -> Optional[Dict[str, str]]:
    """Return the source that could serve this point, or ``None``.

    ``None`` means no verified open source covers it, which is the normal answer
    for every precinct this product serves.
    """
    for idx, (lat_min, lat_max, lon_min, lon_max) in enumerate(_COVERAGE_BOXES):
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return OPEN_LIDAR_COVERAGE[_CODE_BY_BOX[idx]]
    return None


_CODE_BY_BOX = [
    "BE", "CH", "DE", "DK", "EE", "ES", "FI", "FR", "IE", "LU", "LV", "NL", "PL", "SE", "SI", "UK", "US",
]


def coverage_note(lat: float, lon: float) -> str:
    """A one-line, honest statement about LiDAR availability for a point."""
    src = open_lidar_coverage(lat, lon)
    if src is None:
        return NO_COVERAGE_MESSAGE
    return (
        f"An open LiDAR source covers this area: {src['bucket']} ({src['format']}). "
        "This deployment does not currently read it, so the point cloud is still "
        "unavailable here."
    )
