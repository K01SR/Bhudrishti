"""Real ground elevation for the terrain reference layer.

Ground level, building base level and underground depth all have to be measured
against a real surface, otherwise the volumetric model floats on an invented zero
datum. This module reads the AWS Terrain Tiles ("terrarium") raster, a public,
credential-free service that serves global elevation as PNG-encoded tiles. The
underlying sources are the usual public elevation programs (SRTM, Copernicus DEM
and national DEMs), which is why it covers India without any registration.

Only ``zlib`` and ``numpy`` are needed, so no GDAL/rasterio wheel is pulled into
the image for what amounts to a single-pixel windowed read.

Terrarium encoding, per pixel::

    elevation_m = (R * 256 + G + B / 256) - 32768

Sanity check: the Airoli Sector 8 sample resolves to 8.0 m here, which agrees
with an independent Copernicus-derived reading of the same coordinate.

This is terrain, not roof height. It fixes the ground plane; rooftop heights must
still come from a footprint provider or be derived and labelled as modelled.
"""
from __future__ import annotations

import math
import os
import struct
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

from app.sources.base import NoAuthenticSourceError, Provenance

TERRAIN_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium"
TERRAIN_LICENSE = (
    "AWS Terrain Tiles - public-domain elevation sources (SRTM, Copernicus DEM, national DEMs); "
    "free to use with attribution"
)
TERRAIN_DATASET = "AWS Terrain Tiles (global elevation raster, terrarium encoding)"
_USER_AGENT = "BhuDrishti3D/1.0 (3D cadastral prototype; elevation reference)"
_DEFAULT_ZOOM = 12
_TILE_TTL_S = 30 * 24 * 3600


def _cache_dir() -> Path:
    base = Path("/app/data") if Path("/app/data").is_dir() else Path(__file__).resolve().parents[3].parent / "data"
    path = base / "terrain"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _tile_xyz(lat: float, lon: float, zoom: int) -> Tuple[int, int, int, int, int]:
    """Slippy tile and the pixel inside it for a coordinate."""
    scale = 2**zoom
    x = (lon + 180.0) / 360.0 * scale
    lat_rad = math.radians(max(min(lat, 85.05112878), -85.05112878))
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * scale
    tx, ty = int(x), int(y)
    size = 256
    px, py = int((x - tx) * size), int((y - ty) * size)
    return tx, ty, min(max(px, 0), size - 1), min(max(py, 0), size - 1), zoom


def _decode_terrarium(raw: bytes) -> np.ndarray:
    """Decode a terrarium PNG to float elevations in metres."""
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise NoAuthenticSourceError("terrain tile is not a PNG")
    pos, idat, width, height, colour = 8, b"", 0, 0, 0
    while pos + 8 <= len(raw):
        length = struct.unpack_from(">I", raw, pos)[0]
        kind = raw[pos + 4 : pos + 8]
        chunk = raw[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            width, height, _depth, colour = struct.unpack_from(">IIBB", chunk[:10])
        elif kind == b"IDAT":
            idat += chunk
        elif kind == b"IEND":
            break
        pos += 12 + length
    if not width or not height:
        raise NoAuthenticSourceError("terrain tile header is incomplete")

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(colour)
    if channels is None:
        raise NoAuthenticSourceError(f"unsupported terrain tile colour type {colour}")

    data = zlib_decompress(idat)
    stride = width * channels
    out = np.zeros((height, stride), dtype=np.uint8)
    previous = np.zeros(stride, dtype=np.uint8)
    offset = 0
    for row in range(height):
        filter_type = data[offset]
        offset += 1
        line = np.frombuffer(data[offset : offset + stride], dtype=np.uint8).astype(np.int32).copy()
        offset += stride
        if filter_type == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 255
        elif filter_type == 2:
            line = (line + previous) & 255
        elif filter_type == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + int(previous[i])) >> 1)) & 255
        elif filter_type == 4:
            for i in range(stride):
                a = int(line[i - channels]) if i >= channels else 0
                b = int(previous[i])
                c = int(previous[i - channels]) if i >= channels else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                predictor = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + predictor) & 255
        out[row] = line.astype(np.uint8)
        previous = out[row]

    rgba = out.reshape(height, width, channels)
    if channels == 1:
        rgb = np.repeat(rgba, 3, axis=2)
    elif channels == 2:
        rgb = np.repeat(rgba[:, :, :1], 3, axis=2)
    else:
        rgb = rgba[:, :, :3]
    rgb = rgb.astype(np.float64)
    return rgb[:, :, 0] * 256.0 + rgb[:, :, 1] + rgb[:, :, 2] / 256.0 - 32768.0


def zlib_decompress(payload: bytes) -> bytes:
    import zlib

    return zlib.decompress(payload)


class TerrainSource:
    """Ground elevation lookups backed by the public terrain raster."""

    name = "aws-terrain-tiles"

    def __init__(self, zoom: int = _DEFAULT_ZOOM) -> None:
        self.zoom = zoom
        self._tiles: Dict[Tuple[int, int, int], np.ndarray] = {}

    @property
    def is_configured(self) -> bool:
        return True

    def _load_tile(self, tx: int, ty: int, zoom: int) -> np.ndarray:
        key = (zoom, tx, ty)
        cached = self._tiles.get(key)
        if cached is not None:
            return cached

        path = _cache_dir() / f"terrarium_{zoom}_{tx}_{ty}.png"
        raw: Optional[bytes] = None
        if path.exists() and (time.time() - os.path.getmtime(path)) < _TILE_TTL_S and path.stat().st_size > 0:
            raw = path.read_bytes()
        if raw is None:
            request = urllib.request.Request(f"{TERRAIN_URL}/{zoom}/{tx}/{ty}.png", headers={"User-Agent": _USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed host
                    raw = response.read()
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                raise NoAuthenticSourceError(f"terrain tile {zoom}/{tx}/{ty} unavailable: {exc}") from exc
            try:
                path.write_bytes(raw)
            except OSError:
                pass

        grid = _decode_terrarium(raw)
        self._tiles[key] = grid
        return grid

    def elevation_m(self, lat: float, lon: float) -> Optional[float]:
        """Elevation in metres at a coordinate, or None if the tile has no data."""
        tx, ty, px, py, zoom = _tile_xyz(lat, lon, self.zoom)
        try:
            grid = self._load_tile(tx, ty, zoom)
        except NoAuthenticSourceError:
            raise
        if py >= grid.shape[0] or px >= grid.shape[1]:
            return None
        value = float(grid[py, px])
        # Terrarium encodes "no data" as a large negative sentinel.
        return None if value < -1000 else round(value, 2)

    def area_min_max(self, lat: float, lon: float, radius: int) -> Tuple[Optional[float], Optional[float]]:
        """Elevation envelope over a radius, for terrain-aware placement."""
        steps = 5
        low: Optional[float] = None
        high: Optional[float] = None
        for i in range(steps):
            for j in range(steps):
                offset_lat = (i / (steps - 1) - 0.5) * 2 * (radius / 110540.0)
                offset_lon = (j / (steps - 1) - 0.5) * 2 * (radius / 111320.0)
                value = self.elevation_m(lat + offset_lat, lon + offset_lon)
                if value is None:
                    continue
                low = value if low is None else min(low, value)
                high = value if high is None else max(high, value)
        return low, high

    def provenance(self) -> Provenance:
        return Provenance(
            provider=self.name,
            dataset=TERRAIN_DATASET,
            license=TERRAIN_LICENSE,
            source_url=f"{TERRAIN_URL}/{{{self.zoom}}}/{{x}}/{{y}}.png",
            authoritative=False,
        )


_terrain = TerrainSource()


def ground_elevation_m(lat: float, lon: float) -> Optional[float]:
    """Ground elevation in metres, or None when the source cannot be read."""
    try:
        return _terrain.elevation_m(lat, lon)
    except NoAuthenticSourceError:
        return None
