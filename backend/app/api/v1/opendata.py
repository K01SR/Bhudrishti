"""Open-data area endpoints — 3D twins, LiDAR and labels for any area on Earth.

Geometry comes from the configured authentic providers in ``app.sources``
(ISRO/NRSA Bhuvan, data.gov.in, OpenStreetMap), behind a TTL cache so repeated
calls never re-fetch the network. ``POST /opendata/fetch`` forces a fresh pull
and is the "continuous load" hook used by collectors / schedulers to keep
high-traffic regions warm. When no provider can serve an area the endpoint
reports 503 with the reason: no synthetic geometry is ever returned.

``GET /opendata/area`` carries a strong ETag over the bytes it actually sends, so
a full response and a sparse one for the same area are separately identifiable,
and honours ``If-None-Match`` with 304. It accepts ``fields`` to return only the
top-level keys a caller needs, and that selection is part of the representation
the ETag names. ``POST /opendata/prewarm`` warms a nominated set of areas
through the same providers and cache; it changes only when the fetch happens,
not what is served. ``areas`` is optional: omit it and the configured
``OPENDATA_PREWARM_AREAS`` is used instead.
"""
from __future__ import annotations

import io
import json
import struct
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.opendata import service
from app.opendata.overpass import OverpassBusy
from app.sources import NoAuthenticSourceError

router = APIRouter(prefix="/opendata", tags=["opendata"])

_SOURCE_ERROR_STATUS = 503

# What to send when a prewarm request nominates nothing. Two different causes,
# so two messages: "you did not say" and "this deployment does not say either"
# are not the same problem and only one of them is fixed by editing the request.
_PREWARM_UNSET = (
    "No areas to prewarm. The request omitted `areas` and OPENDATA_PREWARM_AREAS "
    "is not set, so this deployment has nominated no area to warm. Pass "
    "`areas=lat,lon[,radius[,max_buildings]]` (semicolon-separated for several) "
    "or set OPENDATA_PREWARM_AREAS. Nothing was fetched."
)
_PREWARM_EMPTY = (
    "No areas to prewarm. OPENDATA_PREWARM_AREAS is set but holds no "
    "`lat,lon[,radius[,max_buildings]]` entry, so the fallback selected nothing. "
    "Pass `areas=` on the request or correct the setting. Nothing was fetched."
)


def _json(payload: dict, etag: str, extra_headers: Optional[dict] = None) -> Response:
    """Serialise a payload once, with the ETag that describes it."""
    headers = {
        "ETag": etag,
        # The payload changes when the provider data does, not on every
        # read, so it may be reused by a cache until the TTL lapses.
        "Cache-Control": f"private, max-age={min(service.CACHE_TTL_S, 3600)}",
    }
    headers.update(extra_headers or {})
    return Response(
        content=json.dumps(payload, default=str, sort_keys=True),
        media_type="application/json",
        status_code=200,
        headers=headers,
    )


def _weak_token(value: str) -> str:
    """An entity-tag reduced to the value it names.

    ``If-None-Match`` is defined to use the *weak* comparison function, so a
    client's ``W/"abc"`` has to match a server's ``"abc"`` and vice versa.
    Comparing the raw strings would silently refuse a perfectly valid
    conditional request from any client that tags weakly.
    """
    token = value.strip()
    if token[:2].upper() == "W/":
        token = token[2:].strip()
    if len(token) >= 2 and token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    return token


def _if_none_match(request: Request, etag: str) -> bool:
    """True when the caller already holds this exact representation.

    The comparison is against the validator for the body this request would send
    -- post-selection, post-projection -- so a 304 can only be issued to a client
    whose cached body is byte-for-byte what is on offer now.
    """
    header = request.headers.get("if-none-match", "")
    candidates = [c.strip() for c in header.split(",") if c.strip()]
    if any(c == "*" for c in candidates):
        return True
    wanted = _weak_token(etag)
    return any(_weak_token(candidate) == wanted for candidate in candidates)


@router.get("/area")
def area(
    request: Request,
    lat: float = Query(..., description="Centre latitude (WGS84)"),
    lon: float = Query(..., description="Centre longitude (WGS84)"),
    radius: int = Query(500, ge=100, le=1500, description="Search radius in metres"),
    max_buildings: int = Query(220, ge=10, le=400, description="Cap on building twins"),
    fields: Optional[str] = Query(
        None,
        description="Comma-separated top-level keys to return (e.g. counts,labels). "
        "region, area, source, provenance and counts are always included.",
    ),
):
    """3D twin payload for any area: buildings + named labels (local meters, origin [200,200]).

    Sends 304 with no body when ``If-None-Match`` matches the current
    representation. The validator is minted after ``fields`` is applied, so the
    full payload and a sparse one never share a tag.
    """
    try:
        payload = service.get_area(lat, lon, radius, max_buildings=max_buildings)
    except NoAuthenticSourceError as exc:
        raise HTTPException(status_code=_SOURCE_ERROR_STATUS, detail=str(exc)) from exc
    except OverpassBusy as exc:
        # A saturated source is a retryable condition, not a missing one, so it
        # gets 503 with the same Retry semantics rather than reading as an
        # outage the caller should give up on.
        raise HTTPException(status_code=_SOURCE_ERROR_STATUS, detail=str(exc)) from exc

    # One pass produces the body and the tag for it, so the two cannot drift.
    body, etag = service.render(payload, fields)
    cache_state = {
        "X-Opendata-From-Cache": "1" if body.get("from_cache") else "0",
        "X-Opendata-Cached-At": str(body.get("cached_at") or ""),
        # Which representation this tag names, so a cache holding both a full
        # and a sparse body can tell them apart without re-deriving anything.
        "X-Opendata-Representation": "sparse" if fields else "full",
    }
    if _if_none_match(request, etag):
        return Response(
            status_code=304,
            headers={
                "ETag": etag,
                "Cache-Control": f"private, max-age={min(service.CACHE_TTL_S, 3600)}",
                **cache_state,
            },
        )
    return _json(body, etag, cache_state)


@router.post("/prewarm")
def prewarm(
    areas: Optional[str] = Query(
        None,
        description="Semicolon-separated lat,lon[,radius[,max_buildings]] entries. "
        "Omit to use OPENDATA_PREWARM_AREAS.",
    ),
):
    """Warm the cache for nominated areas through the configured providers.

    ``areas`` is optional, as documented: omitting it warms the deployment's
    configured set from ``OPENDATA_PREWARM_AREAS`` instead, and ``source`` in the
    response says which of the two was used. When neither nominates anything the
    call fails with the reason rather than reporting a zero-count batch that
    reads like a warm-up which had nothing to do.

    Failures are reported per area and never raised, so one unreachable region
    does not abort the batch or the process.
    """
    if areas and areas.strip():
        return {**service.prewarm_areas(areas), "source": "request:areas"}
    configured = service.prewarm_areas_from_env()
    if configured.get("source") == "unset":
        raise HTTPException(status_code=400, detail=_PREWARM_UNSET)
    if not configured.get("configured") and not configured.get("failed"):
        raise HTTPException(status_code=400, detail=_PREWARM_EMPTY)
    return configured


@router.post("/fetch")
def fetch(
    lat: float = Query(...),
    lon: float = Query(...),
    radius: int = Query(500, ge=100, le=1500),
    max_buildings: int = Query(220, ge=10, le=400),
    force: bool = Query(True, description="Bypass TTL cache and re-pull from the source"),
):
    """Force a fresh open-data pull and warm the cache for this region."""
    try:
        return service.get_area(lat, lon, radius, force=force, max_buildings=max_buildings)
    except NoAuthenticSourceError as exc:
        raise HTTPException(status_code=_SOURCE_ERROR_STATUS, detail=str(exc)) from exc
    except OverpassBusy as exc:
        # A saturated source is a retryable condition, not a missing one, so it
        # gets 503 with the same Retry semantics rather than reading as an
        # outage the caller should give up on.
        raise HTTPException(status_code=_SOURCE_ERROR_STATUS, detail=str(exc)) from exc


@router.get("/lidar")
def lidar_area(
    lat: float = Query(...),
    lon: float = Query(...),
    radius: int = Query(500, ge=100, le=1500),
):
    """JSON point cloud for an area (same shape as ``/lidar/pointcloud``)."""
    try:
        points, meta = service.area_lidar_points(lat, lon, radius)
    except NoAuthenticSourceError as exc:
        raise HTTPException(status_code=_SOURCE_ERROR_STATUS, detail=str(exc)) from exc
    except OverpassBusy as exc:
        # A saturated source is a retryable condition, not a missing one, so it
        # gets 503 with the same Retry semantics rather than reading as an
        # outage the caller should give up on.
        raise HTTPException(status_code=_SOURCE_ERROR_STATUS, detail=str(exc)) from exc
    class_counts: dict = {}
    for p in points:
        class_counts[p.get("classification", 2)] = class_counts.get(p.get("classification", 2), 0) + 1
    return {
        **meta,
        "classifications": {
            "ground": {"count": class_counts.get(2, 0), "color": "#8B7355"},
            "vegetation": {"count": class_counts.get(5, 0), "color": "#2F8F5B"},
            "roof": {"count": class_counts.get(6, 0), "color": "#DC2626"},
            "wall": {"count": class_counts.get(3, 0), "color": "#2563EB"},
        },
        "points": points,
    }


@router.get("/lidar/binary")
def lidar_area_binary(
    lat: float = Query(...),
    lon: float = Query(...),
    radius: int = Query(500, ge=100, le=1500),
):
    """Packed binary point stream for an area (32 bytes/point, 8 floats)."""
    try:
        points, meta = service.area_lidar_points(lat, lon, radius)
    except NoAuthenticSourceError as exc:
        raise HTTPException(status_code=_SOURCE_ERROR_STATUS, detail=str(exc)) from exc
    except OverpassBusy as exc:
        # A saturated source is a retryable condition, not a missing one, so it
        # gets 503 with the same Retry semantics rather than reading as an
        # outage the caller should give up on.
        raise HTTPException(status_code=_SOURCE_ERROR_STATUS, detail=str(exc)) from exc
    buffer = io.BytesIO()
    for p in points:
        buffer.write(struct.pack(
            "<8f",
            float(p["x"]), float(p["y"]), float(p["z"]),
            float(p.get("classification", 2)), float(p.get("intensity", 100)),
            float(p.get("r", 128)), float(p.get("g", 128)), float(p.get("b", 128)),
        ))
    return Response(
        content=buffer.getvalue(),
        media_type="application/octet-stream",
        headers={
            "X-Point-Count": str(len(points)),
            "X-Building-Code": "AREA",
            "X-Data-Type": str(meta.get("data_type", "modelled_from_footprints")),
            "X-Source": str(meta.get("source", "")),
        },
    )


@router.get("/underground")
def underground_area(
    lat: float = Query(..., description="Centre latitude (WGS84)"),
    lon: float = Query(..., description="Centre longitude (WGS84)"),
    radius: int = Query(500, ge=100, le=1500, description="Search radius in metres"),
):
    """Buried assets mapped for the selected area, plus real ground elevation.

    Underground geometry is not published as open data for India, so an area with
    no OpenStreetMap mapping returns an empty layer and an explicit "unmapped"
    note rather than a plausible-looking invented network.
    """
    try:
        return service.area_underground_assets(lat, lon, radius)
    except NoAuthenticSourceError as exc:
        raise HTTPException(status_code=_SOURCE_ERROR_STATUS, detail=str(exc)) from exc
    except OverpassBusy as exc:
        # A saturated source is a retryable condition, not a missing one, so it
        # gets 503 with the same Retry semantics rather than reading as an
        # outage the caller should give up on.
        raise HTTPException(status_code=_SOURCE_ERROR_STATUS, detail=str(exc)) from exc


@router.get("/stats")
def opendata_stats():
    """Cache / fetch telemetry for the open-data registry."""
    return service.stats()