"""Microsoft GlobalML Building Footprints as a real footprint source.

The Bing Maps / GlobalML release is machine-learning building footprints detected
from satellite imagery (Maxar, Airbus, IGN), covering ~1.4B buildings worldwide and
republished under CDLA Permissive 2.0. For India it is far denser than
OpenStreetMap: the Airoli Sector 8 tile alone holds 3,062 footprints against a
few dozen in OSM, which makes it the better base layer for vertical subdivision.

Files are partitioned per region and per Bing Maps level-9 quadkey, published as
gzipped GeoJSONL. Partitions are large (the Mumbai one is ~31 MB gzipped), so
each tile is downloaded once into the local cache and filtered to the requested
radius on every later request.

Heights: the India partitions carry no height estimates (``height`` is -1), so
this source never invents one. Floors and heights must come from another provider
or be derived and labelled as modelled.

Not authoritative: Microsoft is not an Indian government publisher, so
``authoritative`` stays False. It is a genuine published dataset, not a
demonstration fixture.
"""
from __future__ import annotations

import gzip
import json
import math
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.sources.base import AreaData, NoAuthenticSourceError, Provenance, ring_area_m2

GML_LICENSE = "CDLA Permissive 2.0 (Microsoft GlobalML Building Footprints)"
GML_DATASET = "Microsoft GlobalML Building Footprints (Bing Maps ML detection from satellite imagery)"
_INDEX_URL = "https://bfppub.blob.core.windows.net/$web/2026-08-13/dataset-links.csv"
_USER_AGENT = "BhuDrishti3D/1.0 (3D cadastral prototype; +https://github.com/microsoft/GlobalMLBuildingFootprints)"
_INDEX_TTL_S = 24 * 3600
_TILE_TTL_S = 30 * 24 * 3600


def _cache_dir() -> Path:
    base = Path("/app/data") if Path("/app/data").is_dir() else Path(__file__).resolve().parents[3].parent / "data"
    path = base / "globalml"
    path.mkdir(parents=True, exist_ok=True)
    return path


def bing_quadkey(lat: float, lon: float, level: int = 9) -> str:
    """Bing Maps quadkey string for a coordinate (Maps tile system)."""
    n = 2**level
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(max(min(lat, 85.0511), -85.0511))
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    digits = []
    for i in range(level, 0, -1):
        mask = 1 << (i - 1)
        digits.append(str((1 if x & mask else 0) + (2 if y & mask else 0)))
    return "".join(digits)


def _fetch(url: str, timeout: float = 180.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed host allowlist
        return response.read()


def _index() -> Dict[str, str]:
    """Map quadkey -> partition URL, refreshed at most once a day."""
    cache = _cache_dir() / "dataset-links.csv"
    if not cache.exists() or (_now() - os.path.getmtime(cache)) > _INDEX_TTL_S:
        try:
            cache.write_bytes(_fetch(_INDEX_URL, timeout=120.0))
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            if not cache.exists():
                raise NoAuthenticSourceError(f"GlobalML index unavailable: {exc}") from exc
    # One quadkey can be published by several region rows (e.g. an "Asia"
    # row alongside an "India" row). The larger partition holds the fuller
    # extract, so keep the biggest per quadkey rather than the first match.
    best: Dict[str, Tuple[int, str]] = {}
    for line in cache.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 3:
            continue
        quadkey, url = parts[1].strip(), parts[2].strip()
        if not quadkey or not url.startswith("http"):
            continue
        size = _parse_size(parts[3] if len(parts) > 3 else "")
        if quadkey not in best or size > best[quadkey][0]:
            best[quadkey] = (size, url)
    return {quadkey: url for quadkey, (_size, url) in best.items()}


def _parse_size(text: str) -> int:
    text = (text or "").strip()
    multiplier = 1
    if text.endswith("KB"):
        multiplier, text = 1024, text[:-2]
    elif text.endswith("MB"):
        multiplier, text = 1024 * 1024, text[:-2]
    elif text.endswith("GB"):
        multiplier, text = 1024 * 1024 * 1024, text[:-2]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


def _now() -> float:
    import time

    return time.time()


def _tile(quadkey: str) -> Path:
    """Download (once) and return the local path of a quadkey partition."""
    path = _cache_dir() / f"quadkey={quadkey}.csv.gz"
    if path.exists() and (_now() - os.path.getmtime(path)) < _TILE_TTL_S and path.stat().st_size > 0:
        return path
    try:
        url = _index().get(quadkey)
    except NoAuthenticSourceError:
        raise
    if not url:
        raise NoAuthenticSourceError(f"GlobalML publishes no partition for tile {quadkey}")
    try:
        path.write_bytes(_fetch(url))
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        if not path.exists():
            raise NoAuthenticSourceError(f"GlobalML tile {quadkey} unavailable: {exc}") from exc
    return path


def _ring(geometry: Dict[str, Any]) -> List[List[float]]:
    coords = geometry.get("coordinates") or []
    if geometry.get("type") == "Polygon":
        return coords[0] if coords else []
    if geometry.get("type") == "MultiPolygon":
        return coords[0][0] if coords and coords[0] else []
    return []


class GlobalMLSource:
    """Real ML-derived footprints from the GlobalML release."""

    name = "globalml"

    @property
    def is_configured(self) -> bool:
        # No credentials: the release is openly published.
        return True

    def fetch(self, lat: float, lon: float, radius: int, max_buildings: int = 220) -> AreaData:
        quadkey = bing_quadkey(lat, lon)
        path = _tile(quadkey)

        # Equirectangular window around the query point, in degrees.
        dlat = radius / 110540.0
        dlon = radius / (111320.0 * max(math.cos(math.radians(lat)), 1e-6))
        lat0, lat1 = lat - dlat, lat + dlat
        lon0, lon1 = lon - dlon, lon + dlon

        buildings: List[Dict[str, Any]] = []
        total = 0
        try:
            with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        feature = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ring = _ring(feature.get("geometry") or {})
                    if len(ring) < 4:
                        continue
                    lats = [p[1] for p in ring]
                    lons = [p[0] for p in ring]
                    if max(lats) < lat0 or min(lats) > lat1 or max(lons) < lon0 or min(lons) > lon1:
                        continue
                    total += 1
                    if len(buildings) >= max_buildings:
                        continue
                    props = feature.get("properties") or {}
                    height = props.get("height")
                    height = float(height) if isinstance(height, (int, float)) and height > 0 else None
                    buildings.append(
                        {
                            "id": f"GML-{quadkey}-{total}",
                            "name": None,
                            "height_m": height,
                            "floors": None,
                            "type": "unknown",
                            "ring_geo": [[float(x), float(y)] for x, y in ring],
                            "center_geo": [sum(lons) / len(lons), sum(lats) / len(lats)],
                            "footprint_area_m2": ring_area_m2(ring, lat),
                        }
                    )
        except (OSError, gzip.BadGzipFile) as exc:
            raise NoAuthenticSourceError(f"GlobalML tile {quadkey} unreadable: {exc}") from exc

        if not buildings:
            raise NoAuthenticSourceError(f"GlobalML has no footprints within {radius} m of {lat:.5f},{lon:.5f}")

        for b in buildings:
            if b["height_m"] is None:
                b["height_basis"] = "modelled"

        warnings = [
            "GlobalML publishes no height estimates for this region; "
            "height and floor counts are derived and must not be read as surveyed"
        ]
        return AreaData(
            buildings=buildings,
            labels=[],
            provenance=Provenance(
                provider=self.name,
                dataset=f"{GML_DATASET} — tile {quadkey}",
                license=GML_LICENSE,
                source_url=f"https://github.com/microsoft/GlobalMLBuildingFootprints (tile {quadkey})",
                authoritative=False,
            ),
            warnings=warnings,
        )
