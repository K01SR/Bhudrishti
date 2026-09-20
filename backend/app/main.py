import asyncio

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import logging

from app.core.config import settings
from app.core.demo_gate import DemoDataDisabled
from app.api.v1.router import api_router

logger = logging.getLogger("bhudrishti.reads")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        f"{settings.PROJECT_DESCRIPTION}\n\n"
        "3D cadastre and vertical property prototype.\n\n"
        "What is real: administrative place data. The location cascade and place\n"
        "search run on the Local Government Directory (Ministry of Panchayati Raj),\n"
        "covering 677,673 official villages across all 36 states and union\n"
        "territories with their LGD codes, plus official Census 2011 unit counts.\n"
        "Building footprints come from GlobalML and OpenStreetMap, and ground\n"
        "elevation from the AWS terrain raster.\n\n"
        "What is modelled: plot subdivision, floors, heights, FSI arithmetic and\n"
        "volumes. These are derived quantities, not measurements.\n\n"
        "What is synthetic: parcel geometry, identifiers, ownership, ULPIN and any\n"
        "approval, clearance or compliance verdict. None of it is a record of a real\n"
        "property. This is not a government or regulatory system."
    ),
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoopResilientReads(BaseHTTPMiddleware):
    """Retries idempotent read requests once when SQLAlchemy's asyncpg pool
    briefly reuses a connection bound to a stale event loop (uvicorn reload
    churn). Writes are never retried to avoid double side-effects."""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except (DemoDataDisabled, HTTPException):
            raise
        except Exception as exc:  # noqa: BLE001
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                raise
            from asyncio import sleep

            await sleep(0.05)
            try:
                return await call_next(request)
            except (DemoDataDisabled, HTTPException):
                raise
            except Exception as retry_exc:
                # The retry failing is the interesting fact, and it was being
                # discarded in favour of a fixed sentence that named neither
                # error. Log both: the original tells us what the handler was
                # doing, the retry tells us whether the pool actually healed.
                logger.warning(
                    "read retry failed for %s %s",
                    request.method,
                    request.url.path,
                    exc_info=retry_exc,
                )
                logger.debug(
                    "original failure before retry for %s %s",
                    request.method,
                    request.url.path,
                    exc_info=exc,
                )
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Transient backend pool recovery failed, try again.",
                        "error": type(retry_exc).__name__,
                    },
                )


app.add_middleware(LoopResilientReads)


class CompressibleResponseMiddleware(BaseHTTPMiddleware):
    """gzip text-shaped responses; never touch binary ones.

    There was no compression middleware at all. Measured on
    ``GET /api/v1/precinct/buildings?ulpin=12345678901234``:363,381 bytes on the wire, and a request sending
    ``Accept-Encoding: gzip`` got the same 363,381 bytes back with no
    ``Content-Encoding`` header. gzipped, the same body is 21,430 bytes -- a 94%
    reduction, for a map view that refetches on every pan.

    Starlette's ``GZipMiddleware`` was deliberately not used. It compresses by
    response size alone, with no content-type policy, so it would also gzip the
    LiDAR endpoints. Those serve ``application/octet-stream`` records of packed
    float32 -- densely packed binary that gzip cannot meaningfully shrink, so
    the only effect would be CPU burned on every point-cloud request. That is
    the wrong trade precisely on the endpoints under the heaviest load.

    So compression is opt-in by content type: text, JSON and GeoJSON yes,
    already-compressed and binary payloads no. Anything that has already been
    encoded is passed through untouched, which also keeps this correct when it
    sits in front of another compressing layer.
    """

    COMPRESSIBLE_PREFIXES = ("text/",)
    COMPRESSIBLE_TYPES = frozenset(
        {
            "application/json",
            "application/geo+json",
            "application/javascript",
            "application/xml",
            "application/x-javascript",
            "image/svg+xml",
        }
    )
    # Below this, the gzip framing (~18 bytes) plus CPU costs more than it saves.
    MINIMUM_SIZE = 512

    def _should_compress(self, response) -> bool:
        # Checked on the headers, not a `.content_encoding` attribute: under
        # BaseHTTPMiddleware the response is a _StreamingResponse, and the
        # attribute that Starlette's own GZipMiddleware sets is not present
        # here, so an attribute check silently never fired and pre-encoded
        # payloads were compressed a second time.
        if response.headers.get("content-encoding"):
            return False
        ctype = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        if not ctype:
            return False
        return ctype.startswith(self.COMPRESSIBLE_PREFIXES) or ctype in self.COMPRESSIBLE_TYPES

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if "gzip" not in request.headers.get("accept-encoding", "").lower():
            return response
        if not self._should_compress(response):
            return response

        body = getattr(response, "body", None)
        drained = False
        if body is None:
            # BaseHTTPMiddleware hands back a _StreamingResponse, which has no
            # `.body` at all. Treating that as "nothing to compress" is why the
            # first version of this middleware did nothing at all: every
            # response took this branch. The payload is already materialised
            # upstream, so draining the iterator is safe and gives the real body.
            chunks = getattr(response, "body_iterator", None)
            if chunks is None:
                return response
            body = b"".join([chunk async for chunk in chunks])
            drained = True

        def untouched() -> Response:
            """Return the body we drained, or the original response.

            Draining a ``body_iterator`` is destructive: once consumed, the
            original response can no longer produce a body. Returning it anyway
            yields an empty 200. That was not theoretical -- small bodies,
            pre-encoded bodies and incompressible bodies all took a post-drain
            early return and came back empty. So once drained, the bytes are
            re-wrapped in a fresh response rather than handed back.
            """
            if not drained:
                return response
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.headers.get("content-type"),
            )

        if not isinstance(body, (bytes, bytearray)) or len(body) < self.MINIMUM_SIZE:
            return untouched()

        import gzip as _gzip

        # mtime=0 keeps the output byte-stable for identical input, so
        # conditional requests and clients see a deterministic result.
        compressed = _gzip.compress(bytes(body), compresslevel=6, mtime=0)
        # Only pay for it if it actually helped. Small or incompressible bodies
        # can grow once framed.
        if len(compressed) >= len(body):
            return untouched()

        return _GzipResponse(
            compressed,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.headers.get("content-type"),
        )


class _GzipResponse(Response):
    """Minimal response wrapper for an already-gzipped body."""

    def __init__(self, body: bytes, status_code: int, headers: dict, media_type: str | None = None):
        super().__init__(
            content=body,
            status_code=status_code,
            headers={k: v for k, v in headers.items() if k.lower() != "content-length"},
            media_type=media_type,
        )
        self.headers["content-encoding"] = "gzip"
        self.headers["content-length"] = str(len(body))
        self.headers["vary"] = "Accept-Encoding"


app.add_middleware(CompressibleResponseMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)

from app.tiles.tiles import router as tiles_router  # noqa: E402
app.include_router(tiles_router, prefix=settings.API_V1_STR)

from app.tiles.viz import router as viz_router  # noqa: E402
app.include_router(viz_router, prefix=settings.API_V1_STR)

from app.api.v1.ml_status import router as ml_status_router  # noqa: E402
app.include_router(ml_status_router, prefix=settings.API_V1_STR)

from app.api.v1.floor_triage_api import router as floor_triage_router  # noqa: E402
app.include_router(floor_triage_router, prefix=settings.API_V1_STR)


@app.on_event("startup")
async def _register_server_loop():
    """Latch this process's request loop before anything asks for an engine.

    Engine pooling is only safe on a long-lived loop. `get_async_engine()` pools
    when the running loop is the one registered here, and uses NullPool for any
    other loop (chiefly the fresh loop `asyncio.run()` builds per Celery task).
    Registering late would mean the first requests silently ran unpooled.
    """
    from app.core.database import set_server_loop
    set_server_loop(asyncio.get_running_loop())
    logger.info("server loop registered for pooled async engine")


@app.on_event("shutdown")
async def _dispose_engines():
    """Close pooled connections on shutdown instead of orphaning them."""
    from app.core.database import dispose_async_engines
    from app.tiles.tiles import close_tile_pools

    await dispose_async_engines()
    # Tile pools are keyed separately from the ORM engines (raw asyncpg, not
    # SQLAlchemy), so they need closing explicitly. A pool left open at
    # shutdown is what produces the "attached to a different loop" error after
    # a reload, because its connections belong to the loop being replaced.
    await close_tile_pools()


@app.on_event("startup")
async def _prepare_schema():
    """Apply the schema once, at boot, so no read path ever runs DDL.

    `ensure_schema` is idempotent and is still safe to call from code that
    needs it, but it used to be on the request path: every parcel listing took
    an ACCESS EXCLUSIVE lock on `parcels` while ~20 ALTERs ran, so concurrent
    readers queued behind it and, because that DDL ran inline on the event
    loop, the whole server stopped answering. Doing it once here keeps the
    read path read-only.
    """
    try:
        from app.core.cadastre_store import ensure_schema
        await ensure_schema(None)
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("schema preparation deferred: %s", exc)


@app.on_event("startup")
async def _prepare_sample_pointcloud():
    """Materialises the bundled sample point cloud once, at boot.

    `ensure_sample` generates `airoli_s8_hero.las` on demand, but only the
    pipelines data-sets endpoint called it. The LiDAR inspector reads the file
    directly, and the repository copy under `data/` is excluded from the image
    by the build context (the GlobalML archives there are 503 MB). So the
    LiDAR tab returned 503 on a fresh deployment while `/lidar/pointcloud`
    happily served a generated cloud - the two endpoints disagreed about
    whether the sample existed.

    Generating it at boot keeps the inspector and the point-cloud endpoint
    consistent, and it is deterministic (fixed seed) and idempotent.
    """
    try:
        from app.pipelines.sample_data import ensure_sample
        ensure_sample()
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("sample point cloud not generated: %s", exc)


@app.on_event("startup")
async def _seed_national_boundaries():
    """Idempotently ingests the national admin boundary hierarchy at boot."""
    try:
        from app.pipelines.boundary_ingest import ensure_boundaries_seeded
        ensure_boundaries_seeded()
    except Exception as exc:  # noqa: BLE001
        # Non-fatal: /locations/db/* falls back to the static hierarchy.
        import logging
        logging.getLogger(__name__).warning("boundary ingest deferred: %s", exc)


@app.exception_handler(DemoDataDisabled)
async def _demo_data_disabled_handler(request: Request, exc: DemoDataDisabled):
    """Fail closed: refuse generated data instead of serving invented records."""
    body: dict = {"detail": str(exc), "demo_mode": "disabled"}
    note = getattr(exc, "note", None)
    if note:
        # A fact about the data, not about this deployment. Carried separately so
        # a client can tell a shut gate from a dataset nobody publishes.
        body["data_note"] = note
    return JSONResponse(status_code=503, content=body)


@app.get("/")
def root():
    return {
        "platform": settings.PROJECT_NAME,
        "description": settings.PROJECT_DESCRIPTION,
        "status": "OPERATIONAL",
        "version": settings.VERSION,
        "api_documentation": "/docs",
        "canonical_property_endpoint": f"{settings.API_V1_STR}/properties/hero",
        "demo_accounts_endpoint": f"{settings.API_V1_STR}/auth/demo-accounts",
    }


@app.get("/health")
async def health_check():
    """Liveness. Deliberately a coroutine, not a sync def.

    FastAPI runs `def` endpoints in the anyio threadpool, which has a fixed
    size. Several endpoints here do blocking network I/O against external
    services (Overpass, terrain tiles, GlobalML) with timeouts of 10-60s, so
    under a handful of concurrent map loads every thread in the pool parks.
    A sync /health then cannot get a thread either, the container healthcheck
    fails, the container is marked unhealthy, and because `frontend` declares
    `depends_on: backend: condition: service_healthy` the frontend then refuses
    to start. The whole stack looks down while only the threadpool is starved.

    As a coroutine this never touches the threadpool, so liveness stays
    truthful exactly when it matters. Real dependency checking belongs in
    /ready, below.
    """
    return {"status": "HEALTHY", "version": settings.VERSION}


@app.get("/ready")
async def readiness_check():
    """Readiness: the dependencies the product actually needs.

    Separate from /health on purpose. Folding these into /health would restore
    the original failure in a subtler form: a slow dependency would mark the
    process unhealthy and cascade into the frontend, which is the opposite of
    what a readiness probe is for.
    """
    import redis

    checks: dict[str, str] = {}
    try:
        client = redis.Redis(
            host=settings.REDIS_HOST, port=settings.REDIS_PORT, socket_connect_timeout=2
        )
        client.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"unavailable: {type(exc).__name__}"
    try:
        from app.core.database import async_engine
        from sqlalchemy import text

        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"unavailable: {type(exc).__name__}"

    ready = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "READY" if ready else "DEGRADED", "checks": checks},
    )
