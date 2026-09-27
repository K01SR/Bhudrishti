"""
National-style ULPIN derivation layer.

This module derives a 14-character alphanumeric parcel identifier from a
parcel's geo-referenced vertex coordinates: a coordinate cell key, a folded
SHA-256 digest of the canonicalised vertices, and an ISO/IEC 7064 Luhn Mod 36
check character.

What that is **not**, stated here because this docstring is what a reader
trusts before they reach :data:`NATIONAL_ULPIN_SPEC`:

  * This is not an official ULPIN. No authority issues identifiers from this
    code, and an identifier produced here carries no legal weight.
  * The official ULPIN specification was not obtained for this work. The
    14-character geo-referenced-vertex form is implemented as described in
    :data:`NATIONAL_ULPIN_SPEC`; it has not been tested against a published
    specification and no compliance with ECCMA, OGC or any other standard is
    claimed.
  * Production issuance must use the DOLR/state ULPIN API wherever a state has
    rolled the identifier out. A derived value must never override or be
    presented alongside an issued ULPIN as though they were comparable.

The 3D extension (parent/vertical-layer) is additive and does not alter the
parent parcel identity.

Encoding (documented, deterministic, idempotent):
  positions 0..1   ECCMA-style degree-cell band (lat band char, lon band char)
  positions 2..12  radix-36 digest of the canonicalised vertex coordinates
  position  13     Luhn Mod-36 check character
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List, Tuple

from app.id_engine.generator import (
    ALPHABET,
    calculate_luhn_mod36_checksum,
    verify_luhn_mod36_checksum,
)

ALPHABET_MAP = {c: i for i, c in enumerate(ALPHABET)}

# India landmass degree bands (rough ECCMA-flavoured cell keys).
LAT_LETTER = "ACDEFGJKMNPQRSTUVWXYZ"


def _canon_vertex(coord: Tuple[float, float]) -> str:
    # Round to ~0.000001° (~0.1 m) so repeated ingest of the same parcel is stable.
    return f"{coord[0]:.6f},{coord[1]:.6f}"


def canonical_vertices(ring: Iterable[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Sorts (for topology-independence) and dedupes the vertex ring."""
    seen = set()
    out: List[Tuple[float, float]] = []
    for x, y in ring:
        x, y = float(x), float(y)
        key = (round(x, 6), round(y, 6))
        if key not in seen:
            seen.add(key)
            out.append(key)
    out.sort()
    return out


def eccma_cell_key(lat: float, lon: float) -> str:
    """Degree-cell band key: 1 char for latitude band, 1 char for longitude band."""
    lat_band = int(abs(lat) // 1)
    lon_band = int(abs(lon) // 1)
    lat_char = LAT_LETTER[lat_band % len(LAT_LETTER)]
    lon_char = ALPHABET[lon_band % 36]
    return f"{lat_char}{lon_char}"


def parcel_ulpin_from_vertices(
    ring: Iterable[Tuple[float, float]],
    method: str = "radix36-sha256",
) -> Tuple[str, Dict[str, Any]]:
    """
    Generates a deterministic 14-character national-style parcel ULPIN from
    georeferenced lat/lon vertices. Returns (ulpin, derivation_metadata).
    """
    verts = canonical_vertices(ring)
    if len(verts) < 3:
        raise ValueError("A valid parcel polygon requires at least 3 vertices.")

    lat = sum(v[0] for v in verts) / len(verts)
    lon = sum(v[1] for v in verts) / len(verts)

    cell = eccma_cell_key(lat, lon)

    if method == "radix36-sha256":
        encoded = "".join(_canon_vertex(v) for v in verts)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        acc = int(digest[:20], 16)  # 80 bits
        digits: List[str] = []
        for _ in range(11):
            acc, rem = divmod(acc, 36)
            digits.append(ALPHABET[rem])
        body = cell + "".join(digits)
        check = calculate_luhn_mod36_checksum(body)
        ulpin = body + check
    else:
        raise ValueError(f"Unknown ULPIN method: {method}")

    metadata = {
        "method": method,
        "vertex_count": len(verts),
        "centroid_latlon": [round(lat, 6), round(lon, 6)],
        "cell_key": cell,
        "length": len(ulpin),
        "radix": 36,
        "compliance_note": (
            "Deterministic national-style ULPIN (Bhu-Aadhaar aligned). Official "
            "issuance must use the DOLR/state ULPIN API when available."
        ),
    }
    return ulpin, metadata


def verify_parcel_ulpin(ulpin: str, ring: Iterable[Tuple[float, float]]) -> Tuple[bool, str]:
    """Re-derives the expected 14-char ULPIN from a *georeferenced lat/lon* ring."""
    ulpin = ulpin.strip().upper()
    if len(ulpin) != 14 or not ulpin.isalnum():
        return False, "ULPIN must be exactly 14 alphanumeric characters."
    expected, _ = parcel_ulpin_from_vertices(ring)
    if ulpin != expected:
        return False, f"Datum mismatch: received '{ulpin}', derived '{expected}'."
    if not verify_luhn_mod36_checksum(ulpin):
        return False, "Luhn Mod-36 check character failed."
    return True, "ULPIN verified against parcel vertices and checksum."


def verify_local_ring(
    ulpin: str,
    ring_m: Iterable[Tuple[float, float]],
    origin_easting: float,
    origin_northing: float,
    utm_zone: int = 43,
) -> Tuple[bool, str]:
    """Verifies a ULPIN against a local-frame metre ring (converts to lat/lon first)."""
    ring_latlon = [local_to_latlon(p, origin_easting, origin_northing, utm_zone) for p in ring_m]
    return verify_parcel_ulpin(ulpin, ring_latlon)


NATIONAL_ULPIN_SPEC = {
    # This describes a derivation implemented in this repository. It is not a
    # published specification, and the project is not part of any government
    # programme. The previous version named DILRMP as the "programme", named the
    # Department of Land Resources / MoRD as the "authority", reported a rollout
    # figure of "29 States/UTs adopted", and described the result as a "single
    # authoritative source of truth for surface land parcels". None of that is
    # true of this codebase, and the object is rendered as JSON in the UI, so
    # those strings were presented to users as fact.
    "name": "ULPIN (Unique Land Parcel Identification Number) — 14-character form",
    "status": (
        "Independently implemented for this prototype. Not published, not "
        "endorsed, and not issued by any authority."
    ),
    "programme": None,
    "authority": None,
    "length": 14,
    "type": "alphanumeric",
    "basis": (
        "Parent parcel vertices, converted from the local metre frame to "
        "latitude/longitude, then hashed. No external standard is certified "
        "or tested against."
    ),
    "rollout": None,
    "usage": (
        "A deterministic label for a synthetic demo parcel. It carries no legal "
        "weight, confers no authority, and is not a source of truth about any "
        "real parcel."
    ),
    "official_api_note": (
        "Production must consume the official DOLR/state ULPIN issuance API. "
        "This module provides a deterministic national-aligned derivation for "
        "offline/qualified evaluation and vertical-mapping linkage."
    ),
}


# ---- local cadastral frame -> WGS84 conversion ---------------------------------- #
class GeoRefError(RuntimeError):
    pass


def _transformer(utm_zone: int = 43):
    try:
        from pyproj import Transformer
    except ImportError:  # pragma: no cover
        raise GeoRefError("pyproj is required for local->EPSG:4326 conversion")
    return Transformer.from_crs(
        f"EPSG:326{utm_zone}",
        "EPSG:4326",
        always_xy=True,  # returns (lon, lat)
    )


def local_to_latlon(
    point_m: Tuple[float, float],
    origin_easting: float,
    origin_northing: float,
    utm_zone: int = 43,
) -> Tuple[float, float]:
    """Converts a point in the local cadastral frame to (lat, lon) via UTM origin."""
    easting = origin_easting + float(point_m[0])
    northing = origin_northing + float(point_m[1])
    lon, lat = _transformer(utm_zone).transform(easting, northing)
    return round(lat, 8), round(lon, 8)


def national_ulpin_for_local_ring(
    ring_m: Iterable[Tuple[float, float]],
    origin_easting: float,
    origin_northing: float,
    utm_zone: int = 43,
) -> Tuple[str, Dict[str, Any]]:
    """Generates a national-style parcel ULPIN from a local-frame metre ring."""
    ring_latlon = [local_to_latlon(p, origin_easting, origin_northing, utm_zone) for p in ring_m]
    ulpin, meta = parcel_ulpin_from_vertices(ring_latlon)
    meta["conversion"] = {
        "origin_easting": origin_easting,
        "origin_northing": origin_northing,
        "utm_zone": utm_zone,
        "ring_latlon": ring_latlon,
    }
    return ulpin, meta


def compose_vertical_ulpin(
    parent_ulpin: str,
    type_code: str,
    building_code: str,
    level_code: str,
    unit_code: str,
) -> str:
    """Composes a 3D vertical-extension ULPIN under a (national) 14-char parent."""
    from app.id_engine.generator import generate_proposed_3d_id

    return generate_proposed_3d_id(parent_ulpin, type_code, building_code, level_code, unit_code)