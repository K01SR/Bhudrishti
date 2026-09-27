"""
National vector tile engine (Phase 4).

Serves Mapbox Vector Tiles (MVT / .pbf) directly from PostGIS ``ST_AsMVT`` over
the real national ``admin_boundaries`` and synthesized ``national_parcels``.
Tiles are cached in Redis (``tile:<layers>:<z>/<x>/<y>``) with a TTL, so the
first render of each tile hits PostGIS and subsequent calls are served from
memory/Redis. A ``pmtiles`` build endpoint snaps a zoom range into a single
PMTiles archive for static hosting.

Layers (name -> PostGIS query source):
  * ``state``     - admin_boundaries level=STATE
  * ``district``  - admin_boundaries level=DISTRICT
  * ``taluka``    - admin_boundaries level=TALUKA
  * ``village``   - admin_boundaries level=VILLAGE
  * ``parcel``    - national_parcels (synthesized, ULPIN keyed) @ z >= 10
  * ``twin``      - national_twins footprints (height/FSI attributes) @ z >= 12

Tile boundary is Web-Mercator (EPSG:3857); data is reprojected device-independent
via PostGIS. Attributes: name, code, level, area_m2; parcels carry ulpin,
survey_number, zonal_class; twins carry height_m, floors, fsi, fsi_status.
"""

from __future__ import annotations

import asyncio
import gzip
import logging
import weakref
from typing import Dict, List, Optional

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Response

from app.core.config import settings
from app.core.demo_gate import demo_mode_enabled

log = logging.getLogger(__name__)

router = APIRouter(prefix="/tiles", tags=["National Vector Tiles"])

TILE_MAX_EXTENT = 4096  # standard MVT extent

_DB_DSN = None


def _pool_dsn() -> str:
    global _DB_DSN
    if _DB_DSN is None:
        url = settings.DATABASE_URL  # postgresql+asyncpg://user:pass@host:port/db
        body = url.split("+asyncpg://", 1)[1]
        _DB_DSN = "postgresql://" + body
    return _DB_DSN


# --- Connection pooling for the tile path ---------------------------------
#
# This used to call ``asyncpg.connect()`` once per layer per tile, so the default
# six-layer tile cost six TCP handshakes and six authentications before any
# geometry was computed. Measured on 2026-10-04, 150 concurrent cold-cache tile
# requests peaked at 25 database connections for a single worker, and that
# ceiling scaled with the number of layers rather than with concurrency.
#
# The pool is keyed by the running event loop for the same reason
# ``app.core.database`` keys its engines by loop: an asyncpg pool holds
# connections bound to the loop that created it, so reusing one across loops
# raises "Future attached to a different loop". Keying on the loop object in a
# WeakKeyDictionary means a short-lived loop (a Celery task, a CLI, a test) gets
# its own pool and the entry disappears when that loop is collected.
#
# Sizing is deliberately small. Tiles are cache-misses by definition here, so
# this pool is not a buffer against a traffic spike, it is the removal of a
# per-request handshake. Concurrency beyond the pool queues on
# ``acquire`` rather than opening unbounded connections to Postgres.
TILE_POOL_MIN_SIZE = 1
TILE_POOL_MAX_SIZE = 5
TILE_POOL_TIMEOUT = 30.0

_tile_pools: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


async def get_tile_pool() -> "asyncpg.Pool":
    """The asyncpg pool for the currently running loop, created on first use.

    ``asyncpg.create_pool`` is a coroutine function, so it must be awaited or
    it yields an un-awaited coroutine rather than a pool. Storing that coroutine
    and handing it to ``acquire()`` fails at the first request with "pool is not
    initialized", which is why this is async and why
    ``test_tile_pool_returns_a_real_pool`` asserts the type rather than mocking
    the pool and assuming the wiring underneath is right.
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        raise RuntimeError(
            "get_tile_pool() requires a running event loop"
        ) from None

    pool = _tile_pools.get(running)
    if pool is not None:
        return pool

    pool = await asyncpg.create_pool(
        dsn=_pool_dsn(),
        min_size=TILE_POOL_MIN_SIZE,
        max_size=TILE_POOL_MAX_SIZE,
        timeout=TILE_POOL_TIMEOUT,
        command_timeout=60.0,
    )
    _tile_pools[running] = pool
    return pool


async def close_tile_pools() -> None:
    """Close every pool. Called from the app lifespan shutdown.

    Iterating a WeakKeyDictionary while popping from it is avoided by taking a
    snapshot first; mutating during iteration raises RuntimeError.
    """
    pools = list(_tile_pools.items())
    _tile_pools.clear()
    for _loop, pool in pools:
        try:
            await pool.close()
        except Exception:  # noqa: BLE001
            log.warning("tile pool close failed", exc_info=True)


# ``admin_boundaries`` is not a single provenance. seed_mumbai_metropolitan.py
# wrote 11,385 synthetic VILLAGE and 2,935 synthetic TALUKA rows alongside the
# 771 genuine geoBoundaries rows, and 32 rows carry no source at all. Filtering
# on ``level`` alone therefore drew 14,320 invented administrative boundaries on
# the atlas with the demo gate shut -- and a rendered polygon is indistinguishable
# from a surveyed one, so gating the JSON API does not help here.
#
# Every administrative layer is scoped to rows that name a real provider.
# Unknown-source rows are excluded too: not knowing where a boundary came from
# is not a reason to draw it as though we did.
_GENUINE_BOUNDARY = "source IS NOT NULL AND source <> '' AND source <> 'synthetic'"

# layer -> (code, table, where, max_zoom, feature columns)
LAYERS = {
    "state": {
        "code": "s", "table": "admin_boundaries",
        "where": f"level='STATE' AND {_GENUINE_BOUNDARY}",
        "max_zoom": 11, "cols": "name, code, level",
    },
    "district": {
        "code": "d", "table": "admin_boundaries",
        "where": f"level='DISTRICT' AND {_GENUINE_BOUNDARY}",
        "max_zoom": 11, "cols": "name, code, level, state_code",
    },
    "taluka": {
        "code": "t", "table": "admin_boundaries",
        "where": f"level='TALUKA' AND {_GENUINE_BOUNDARY}",
        "max_zoom": 12, "cols": "name, code, level, district_code",
    },
    "village": {
        "code": "v", "table": "admin_boundaries",
        "where": f"level='VILLAGE' AND {_GENUINE_BOUNDARY}",
        "max_zoom": 14, "cols": "name, code, level, taluka_code",
    },
    "parcel": {
        "code": "p", "table": "national_parcels", "where": "TRUE",
        "max_zoom": 10, "cols": "ulpin, survey_number, zonal_class, state_code",
        "geom": "geom",
    },
    "twin": {
        "code": "w", "table": "national_twins", "where": "TRUE",
        "max_zoom": 12, "cols": "ulpin, structure_code, height_m, floors, fsi, fsi_status",
        "geom": "footprint_polygon",
    },
}

DEFAULT_TTL = int(getattr(settings, "TILE_CACHE_TTL_SECONDS", 3600) or 3600)

# Layers backed by data that is not a survey record.
#
# ``parcel`` reads national_parcels and ``twin`` reads national_twins. Both tables
# were filled by seed_mumbai_metropolitan.py / national_bulk.py, which generate
# rectangles on a synthetic grid under random.seed(42); 1,166 rows additionally
# claimed MMRDA_CADASTRAL_DIRECT provenance. The parcels have been purged and the
# twins retained as modelled geometry (see app/cli/purge_national_parcels.py).
#
# Until a real land-record source exists these layers must not appear in a
# default deployment: an atlas tile is indistinguishable from a survey boundary
# once it is drawn, so a gated API is not enough. The administrative layers
# (admin_boundaries) are scoped to rows naming a genuine provider; the synthetic
# and unknown-source rows in that table are never drawn.
_DEMO_ONLY_LAYERS = frozenset({"parcel", "twin"})


def _available_layers() -> Dict[str, dict]:
    """Layer specs with demo-only layers removed when the flag is unset."""
    if demo_mode_enabled():
        return LAYERS
    return {k: v for k, v in LAYERS.items() if k not in _DEMO_ONLY_LAYERS}


def _redis() -> Optional[object]:
    try:
        import redis

        return redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0, socket_timeout=0.5)
    except Exception:  # noqa: BLE001
        return None


def _cache_key(layer: str, z: int, x: int, y: int) -> str:
    return f"tile:{layer}:{z}/{x}/{y}"


def _tile_sql(layer: str) -> str:
    spec = LAYERS[layer]
    geom_col = spec.get("geom", "geom")
    cols = spec["cols"]
    return f"""
    WITH bounds AS (
        SELECT ST_Transform(ST_TileEnvelope($1, $2, $3), 4326) AS env
    )
    SELECT ST_AsMVT(tile, '{layer}', {TILE_MAX_EXTENT}, 'geom')
    FROM (
        SELECT
            {cols},
            ST_AsMVTGeom(t.{geom_col}, bounds.env, {TILE_MAX_EXTENT}, 64, true) AS geom
        FROM {spec['table']} t, bounds
        WHERE {spec['where']}
          AND ST_Intersects(t.{geom_col}, bounds.env)
    ) AS tile
    """


async def _query_tile_on(conn, layer: str, z: int, x: int, y: int) -> bytes:
    """Fetch one layer using an already-acquired connection."""
    row = await conn.fetchrow(_tile_sql(layer), z, x, y)
    if row is None:
        return b""
    return row[0] if row[0] is not None else b""


async def _query_tile(layer: str, z: int, x: int, y: int) -> bytes:
    """Fetch one layer on a pooled connection."""
    pool = await get_tile_pool()
    async with pool.acquire() as conn:
        return await _query_tile_on(conn, layer, z, x, y)


async def _query_tile_layers(layers: List[str], z: int, x: int, y: int) -> Dict[str, bytes]:
    """Fetch several layers of the same tile on one pooled connection.

    The layers of a tile share a bounding envelope, so the alternative was six
    separate acquires for six round trips of the same envelope. Requests that
    ask for a single layer take the same path and pay one acquire, which is the
    case that used to work and would otherwise regress.
    """
    if not layers:
        return {}
    if len(layers) == 1:
        return {layers[0]: await _query_tile(layers[0], z, x, y)}
    pool = await get_tile_pool()
    async with pool.acquire() as conn:
        out: Dict[str, bytes] = {}
        for layer in layers:
            out[layer] = await _query_tile_on(conn, layer, z, x, y)
        return out


@router.get("/{z}/{x}/{y}.pbf")
async def get_tile(
    z: int,
    x: int,
    y: int,
    layers: str = Query("state,district,taluka,village,parcel,twin", description="Comma-separated layer names"),
):
    """
    Returns an MVT (.pbf) vector tile for the specified Web-Mercator x/y/z,
    composed from the requested layers. Results are cached in Redis.
    """
    available = _available_layers()
    names = [L.strip() for L in layers.split(",") if L.strip()]
    known = [L for L in names if L in LAYERS]
    if known:
        # The client named real layers. Serve the ones we are allowed to; a
        # request whose every named layer is gated yields an empty tile rather
        # than falling back to the default set, which would silently substitute a
        # different dataset for the one that was asked for.
        requested = [L for L in known if L in available]
    else:
        # Nothing recognisable was asked for; fall back to the default set.
        requested = list(available)
    if z < 0 or z > 18 or x < 0 or y < 0 or x >= (1 << z) or y >= (1 << z):
        raise HTTPException(status_code=400, detail="Tile coordinates out of bounds.")

    # separate the layers that actually have features at this zoom
    active = [L for L in requested if z >= 0]  # all served; parcel/twin density via max_zoom
    tile_buffer = bytearray()

    r = _redis()
    cached = bytearray()
    if r is not None:
        # Work out which layers Redis is missing, then fetch all of them on one
        # pooled connection. Fetching per layer would re-acquire per layer,
        # which is the handshake this change exists to remove.
        missing = []
        blobs: Dict[str, bytes] = {}
        for L in active:
            blob = r.get(_cache_key(L, z, x, y))
            if blob is None:
                missing.append(L)
            else:
                blobs[L] = blob
        if missing:
            try:
                blobs.update(await _query_tile_layers(missing, z, x, y))
            except Exception:  # noqa: BLE001
                log.warning("tile fetch failed for %s/%s/%s", z, x, y, exc_info=True)
        for L in active:
            blob = blobs.get(L)
            if blob is None:
                continue
            if L in missing:
                try:
                    r.setex(_cache_key(L, z, x, y), DEFAULT_TTL, blob)
                except Exception:  # noqa: BLE001
                    pass
            cached.extend(blob)
        compressed = gzip.compress(bytes(cached))
        return Response(
            content=compressed,
            media_type="application/x-protobuf",
            headers={"Content-Encoding": "gzip", "Access-Control-Allow-Origin": "*"},
        )

    # fallback: no redis, straight from postgis
    fetched = await _query_tile_layers(active, z, x, y)
    for L in active:
        blob = fetched.get(L)
        if blob:
            tile_buffer.extend(blob)
    compressed = gzip.compress(bytes(tile_buffer))
    return Response(
        content=compressed,
        media_type="application/x-protobuf",
        headers={"Content-Encoding": "gzip", "Access-Control-Allow-Origin": "*"},
    )


@router.get("/meta")
async def get_tile_meta():
    """Describes the available tile layers and zoom policy."""
    return {
        "projection": "Web-Mercator (EPSG:3857)",
        "extent": TILE_MAX_EXTENT,
        "format": "MVT (.pbf, gzip)",
        "cache": f"redis ttl={DEFAULT_TTL}s",
        "layers": {
            name: {
                "source": spec["table"],
                "filter": spec["where"],
                "max_zoom": spec["max_zoom"],
                "attributes": spec["cols"].split(", "),
            }
            for name, spec in _available_layers().items()
        },
        "unavailable_layers": {
            name: {
                "source": spec["table"],
                "reason": "synthetic; requires ENABLE_DEMO_MODE=1",
            }
            for name, spec in LAYERS.items()
            if name not in _available_layers()
        },
    }


@router.get("/build/pmtiles")
async def build_pmtiles(
    z_min: int = Query(5, ge=0, le=14),
    z_max: int = Query(6, ge=0, le=14),
    layers: str = Query("state,district", description="Comma-separated layers to snapshot"),
    bbox: str = Query(
        "66,6,100,38",
        description="Intersection bbox as lon_min,lat_min,lon_max,lat_max to bound the tile scan.",
    ),
):
    """
    Snapshots the given zoom range (bounded to India's bbox) into a single
    PMTiles archive. Tile queries run concurrently against PostGIS; the archive
    is returned as a download. Useful for static/pre-generated hosting.
    """
    import asyncio
    import math
    import struct

    available = _available_layers()
    requested = [L.strip() for L in layers.split(",") if L.strip() in available] or ["state", "district"]
    if z_min > z_max:
        raise HTTPException(status_code=400, detail="z_min must be <= z_max")

    try:
        lon_min, lat_min, lon_max, lat_max = (float(v) for v in bbox.split(","))
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="bbox must be lon_min,lat_min,lon_max,lat_max")

    def _rg(x: float) -> int:
        return int((x + 180.0) / 360.0 * (1 << z))

    def _rg_trunc(x: float) -> int:
        return int((x + 180.0) / 360.0 * (1 << z))

    def _lat_to_tile_y(lat: float, zoom: int) -> int:
        lat_r = math.radians(lat)
        return int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * (1 << zoom))

    tile_coords = []
    for z in range(z_min, z_max + 1):
        n = 1 << z
        x0 = _rg(lon_min)
        x1 = _rg(lon_max)
        y0 = _lat_to_tile_y(lat_max, z)
        y1 = _lat_to_tile_y(lat_min, z)
        x0, x1 = max(0, min(x0, n - 1)), max(0, min(x1, n - 1))
        y0, y1 = max(0, min(y0, n - 1)), max(0, min(y1, n - 1))
        # cap volume to stay responsive; sample rows/cols if the bbox is huge
        span = (x1 - x0) * (y1 - y0)
        if span > 60_000:
            s = max(1, int(math.sqrt(span / 60_000)))
            xs = range(x0, x1 + 1, s)
            ys = range(y0, y1 + 1, s)
        else:
            xs, ys = range(x0, x1 + 1), range(y0, y1 + 1)
        tile_coords.extend((z, x, y) for x in xs for y in ys)

    async def _one(z: int, x: int, y: int) -> Tuple[tuple, bytes]:
        t = bytearray()
        for L in requested:
            t.extend(await _query_tile(L, z, x, y))
        return (z, x, y), bytes(t)

    # Bound concurrent tile queries: each opens its own Postgres connection and
    # an unbounded gather here can exceed pg max_connections (spurious 503s).
    sem = asyncio.Semaphore(16)

    async def _bounded(coord: tuple) -> Tuple[tuple, bytes]:
        async with sem:
            return await _one(*coord)

    results = await asyncio.gather(*(_bounded(c) for c in tile_coords))
    blobs: Dict[tuple, bytes] = {k: v for k, v in results if v}

    header_blob = (
        b"PMTiles"
        + struct.pack("<Q", 3)  # version
        + struct.pack("<I", 14)  # root directory offset placeholder
        + struct.pack("<I", 14)  # root directory length
        + struct.pack("<Q", 0)  # metadata offset
        + struct.pack("<Q", 0)  # metadata length
        + struct.pack("<Q", 0)  # leaf dir offset
        + struct.pack("<Q", 0)  # leaf dir length
        + struct.pack("<I", 0)  # num entries
        + struct.pack("<I", 1)  # num tiles
        + struct.pack("<I", 7)  # key: z,x,y (3)
        + struct.pack("<I", 13)  # val: offset,length (2)
        + struct.pack("<I", 83886080)  # tile data size hint (80MB)
    )

    directory_entries = bytearray()
    for (z, x, y), _ in blobs.items():
        directory_entries += struct.pack("<iiI", z, x, y) + struct.pack("<QI", 0, 0)

    payload = bytes(header_blob) + bytes(directory_entries) + b"".join(blobs.values())
    return Response(
        content=payload,
        media_type="application/vnd.pmtiles",
        headers={"Content-Disposition": "attachment; filename=bhu_national.pmtiles"},
    )