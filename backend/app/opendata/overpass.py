"""OpenStreetMap Overpass fetcher for arbitrary areas.

Thin, dependency-light client over the public Overpass API. Returns building
footprints (with heights when tagged) and named places for a radius around a
geographic point. Output is normalised to plain dicts; all projections to the
local cadastral frame happen in :mod:`app.opendata.service`.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Any, Dict, List, Optional

import httpx

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# Overpass etiquette + WAF compliance: a descriptive User-Agent is mandatory
# (default client UAs are rejected with 406 Not Acceptable).
USER_AGENT = "Bhudrishti3D-Cadastre/1.0 (SIH 2026 platform; contact: platform@bhudrishti.in)"

BUILDING_QUERY = """[out:json][timeout:60];
way["building"](around:{radius},{lat},{lon});
out body geom {maxsize};"""

LABEL_QUERY = """[out:json][timeout:40];
(
  nwr["name"]["amenity"](around:{radius},{lat},{lon});
  nwr["name"]["shop"](around:{radius},{lat},{lon});
  nwr["name"]["tourism"](around:{radius},{lat},{lon});
  nwr["name"]["leisure"](around:{radius},{lat},{lon});
  nwr["name"]["place"](around:{radius},{lat},{lon});
);
out center {labelcap};"""

_BUILDING_KINDS = {
    "residential": "tower",
    "apartments": "tower",
    "house": "row_house",
    "terrace": "row_house",
    "detached": "row_house",
    "office": "commercial",
    "commercial": "commercial",
    "retail": "commercial",
    "school": "commercial",
    "university": "commercial",
    "hospital": "commercial",
    "industrial": "commercial",
    "warehouse": "commercial",
    "hotel": "tower",
    "mixed_use": "tower",
    "yes": "tower",
}


def _tag_height(way: Dict[str, Any]):
    """Best-effort height / floor-count guess from OSM tags."""
    tags = way.get("tags", {}) or {}
    raw_h = tags.get("height") or tags.get("est_height")
    if raw_h:
        try:
            return max(3.0, float(raw_h))
        except ValueError:
            pass
    raw_h = tags.get("building:height")
    if raw_h:
        try:
            return max(3.0, float(raw_h))
        except ValueError:
            pass
    floors = tags.get("building:levels")
    try:
        n = int(float(floors))
    except (TypeError, ValueError):
        n = 2 if tags.get("building") == "house" else 4
    return max(3.0, n * 3.2)


def _floors(way: Dict[str, Any], height_m: float) -> int:
    tags = way.get("tags", {}) or {}
    raw = tags.get("building:levels")
    try:
        return max(1, int(float(raw)))
    except (TypeError, ValueError):
        return max(1, round(height_m / 3.5))


def _element_center(el: Dict[str, Any]) -> Optional[List[float]]:
    """Normalise an Overpass element position to [lon, lat].

    ``out center`` yields ``center`` as an object (``{"lat":..,"lon":..}``) in
    JSON, while nodes carry plain ``lat``/``lon`` fields.
    """
    c = el.get("center")
    if isinstance(c, dict):
        if c.get("lon") is None or c.get("lat") is None:
            return None
        return [float(c["lon"]), float(c["lat"])]
    if isinstance(c, (list, tuple)) and len(c) >= 2 and c[0] is not None and c[1] is not None:
        return [float(c[0]), float(c[1])]
    if el.get("lon") is not None and el.get("lat") is not None:
        return [float(el["lon"]), float(el["lat"])]
    return None


def _way_center(way: Dict[str, Any]) -> Optional[List[float]]:
    geom = way.get("geometry") or []
    if not geom:
        return None
    return [sum(p["lon"] for p in geom) / len(geom), sum(p["lat"] for p in geom) / len(geom)]


_request_lock = threading.Lock()
_last_request_ts = 0.0
_MIN_GAP_S = 5.0
# Ceiling on Overpass fetches in flight. The 5s politeness gap already limits
# the request *rate*; this limits how many callers can be parked waiting for
# their turn. Without it a burst of concurrent area loads each holds a worker
# thread for the whole queue, and the queue is what turns a slow source into a
# hung service. Callers that cannot get a slot promptly are told the source is
# busy rather than being made to wait.
_MAX_INFLIGHT = 6
_inflight = threading.Semaphore(_MAX_INFLIGHT)
# Overpass answers 429 (slot exhausted) / 504 (gateway timeout) when a shared
# client IP hammers it; those are transient and deserve a backoff, not a mirror
# switch that burns the other mirrors' slots too.
_THROTTLED_STATUS = {429, 504}

# Total wall-clock budget for one area fetch (buildings + labels).
AREA_FETCH_BUDGET_S = 30.0


class OverpassBusy(RuntimeError):
    """Raised when no Overpass fetch slot frees up promptly.

    A distinct type so the caller can answer 503 "busy, retry" instead of
    reporting the area as permanently unfetchable.
    """


def _throttle() -> None:
    """Global politeness gate — one network fetch at a time, ≥5s apart.

    The sleep used to happen *inside* `_request_lock`, which turned the lock
    into a five-second parking space: every other caller blocked on the lock
    itself rather than on its own wait, so the queue could not be inspected,
    ordered, or bounded from outside. The reservation is now taken under the
    lock and the wait is spent outside it.

    The caller is assumed to already hold an `_inflight` slot.
    """
    global _last_request_ts
    with _request_lock:
        now = time.monotonic()
        earliest = _last_request_ts + _MIN_GAP_S
        # Claim this caller's slot in the future and move the cursor past it,
        # so concurrent callers are spaced deterministically instead of all
        # being handed the same `earliest` and released together.
        _last_request_ts = max(now, earliest)
        my_slot = _last_request_ts
    wait = my_slot - time.monotonic()
    if wait > 0:
        time.sleep(wait)


def _run_query(
    query: str,
    timeout: float = 20.0,
    attempts: int = 2,
    deadline: Optional[float] = None,
) -> Dict[str, Any]:
    """POST a query to each mirror until one returns a usable element set.

    Retries once with a backoff when a mirror reports a transient throttle so a
    single busy slot does not turn into a total area failure. ``deadline`` is an
    absolute ``time.monotonic()`` budget: once it passes, no further network
    attempt is made, which keeps a fetch bounded even when every mirror stalls.
    """
    last_err: Optional[Exception] = None
    # Bounded admission, taken once for the whole call. If the source is already
    # saturated we say so immediately rather than joining a queue whose length
    # grows with the number of concurrent callers — that queue is what turns a
    # slow source into a hung service.
    if not _inflight.acquire(blocking=False):
        raise OverpassBusy(f"Overpass already has {_MAX_INFLIGHT} fetches in flight")
    try:
        for attempt in range(attempts):
            _throttle()
            for url in OVERPASS_URLS:
                remaining = _remaining(deadline)
                if remaining is not None and remaining <= 0.5:
                    raise RuntimeError(f"Overpass budget exhausted: {last_err}")
                try:
                    resp = httpx.post(
                        url,
                        data={"data": query},
                        headers={"User-Agent": USER_AGENT},
                        timeout=timeout if remaining is None else max(3.0, min(timeout, remaining)),
                    )
                    if resp.status_code in _THROTTLED_STATUS:
                        try:
                            wait = float(resp.headers.get("Retry-After") or 0)
                        except ValueError:
                            wait = 0.0
                        last_err = RuntimeError(f"{url} -> HTTP {resp.status_code}")
                        nap = wait or 8.0
                        if attempt < attempts - 1 and _can_wait(deadline, nap):
                            time.sleep(nap)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    # Some mirrors answer 200 with an HTML/error body; validate shape.
                    if isinstance(data, dict) and isinstance(data.get("elements"), list):
                        return data
                    last_err = RuntimeError(f"malformed response from {url}")
                except Exception as e:  # noqa: BLE001 - try the next mirror before failing
                    last_err = e
                    continue
    finally:
        _inflight.release()
    raise RuntimeError(f"Overpass unreachable: {last_err}")


def _remaining(deadline: Optional[float]) -> Optional[float]:
    return None if deadline is None else deadline - time.monotonic()


def _can_wait(deadline: Optional[float], seconds: float) -> bool:
    """True when the remaining budget still allows sleeping ``seconds``."""
    remaining = _remaining(deadline)
    return remaining is None or remaining > seconds + 0.5


def fetch_osm_area(
    lat: float,
    lon: float,
    radius: int,
    max_buildings: int = 220,
    budget_s: float = AREA_FETCH_BUDGET_S,
) -> Dict[str, Any]:
    """Fetch buildings + named places around (lat, lon).

    Returns ``{"buildings": [...], "labels": [...], "fetched_at": iso}``.
    Buildings carry ``id``, ``name``, ``height_m``, ``floors``, ``type``,
    ``ring_geo`` ([[lon, lat], ...]) and ``center_geo``.

    Buildings and named places are fetched as two independent requests: the
    building footprints are the critical payload, so a failing/garbage label
    response (common in very dense cores) degrades to zero labels instead of
    losing the whole area.
    """
    radius = max(100, min(1500, int(radius)))
    max_buildings = max(10, min(400, int(max_buildings)))
    label_cap = min(2000, max(300, max_buildings * 5))

    # Hard budget for the whole area: a stalled mirror must never hold the API
    # request open. Buildings get the first slice, labels only the remainder.
    deadline = time.monotonic() + max(5.0, float(budget_s))

    building_data = _run_query(
        BUILDING_QUERY.format(radius=radius, lat=lat, lon=lon, maxsize=max_buildings),
        deadline=deadline,
    )
    try:
        label_data = _run_query(
            LABEL_QUERY.format(radius=radius, lat=lat, lon=lon, labelcap=label_cap),
            timeout=12.0,
            attempts=1,
            deadline=deadline,
        )
    except Exception:  # noqa: BLE001 - labels are best-effort
        label_data = {"elements": []}

    buildings: List[Dict[str, Any]] = []
    labels: List[Dict[str, Any]] = []

    for el in building_data.get("elements", []):
        if el.get("type") != "way" or not (el.get("tags") or {}).get("building"):
            continue
        geom = el.get("geometry") or []
        if len(geom) < 3:
            continue
        ring = [[p["lon"], p["lat"]] for p in geom]
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        if not geometry_touches_radius(ring, lat, lon, radius):
            continue
        h = _tag_height(el)
        name = (el.get("tags") or {}).get("name") or f"OSM Building {el['id']}"
        kind = (el.get("tags") or {}).get("building", "yes")
        buildings.append({
            "id": el["id"],
            "name": name[:80],
            "height_m": round(h, 1),
            "floors": _floors(el, h),
            "type": _BUILDING_KINDS.get(kind, "tower"),
            "ring_geo": ring,
            "center_geo": _way_center(el),
        })
        if len(buildings) >= max_buildings:
            break

    labels.extend(_parse_labels(label_data.get("elements", [])))
    uniq = labels

    return {
        "buildings": buildings,
        "labels": uniq,
        "fetched_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


def fetch_osm_labels(
    lat: float,
    lon: float,
    radius: int,
    cap: int = 300,
    budget_s: float = 40.0,
) -> List[Dict[str, Any]]:
    """Named places for an area, without asking for any buildings.

    :func:`fetch_osm_area` spends its budget on footprints first and gives
    labels only what is left, with a single attempt. That is the right priority
    when the caller wanted both, but it is the wrong shape for a caller that
    already has footprints from another provider and only needs names: the
    building query is a large, expensive round-trip whose results are discarded,
    and the label query then has to win whatever budget the discarded query left
    behind.

    Measured on this deployment, that made label top-up succeed roughly half the
    time - the failure surfaced as an area with 220 buildings and no names at
    all, which is indistinguishable from a place that genuinely has no named
    places. Spending the whole budget on the one query that matters, and
    retrying it, removes both the waste and the coin-flip.
    """
    # The budget has to cover the throttle, not just the network. ``_throttle``
    # holds every Overpass call on this process to >=5s apart and is re-taken
    # before each attempt, so a retried call spends most of a tight budget asleep
    # and then reports "budget exhausted" - a self-inflicted timeout that reads
    # exactly like an overloaded mirror. Two attempts at 15s inside 40s leaves
    # room for the wait and still fails fast when the mirror is genuinely gone.
    deadline = time.monotonic() + max(5.0, float(budget_s))
    data = _run_query(
        LABEL_QUERY.format(radius=radius, lat=lat, lon=lon, labelcap=cap),
        timeout=15.0,
        attempts=2,
        deadline=deadline,
    )
    return _parse_labels(data.get("elements", []))


def _parse_labels(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Turn Overpass label elements into named places, de-duplicated.

    Shared by the combined area fetch and the label-only top-up so the two can
    never disagree about what counts as a label.
    """
    out: List[Dict[str, Any]] = []
    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue
        kind = next(
            (k for k in ("amenity", "shop", "tourism", "leisure") if tags.get(k)),
            None,
        )
        if kind is None and not (tags.get("place") or tags.get("highway") or tags.get("building")):
            continue
        # ``out center`` returns a centre for ways/relations; nodes carry lat/lon.
        if el.get("type") == "way":
            c = _way_center(el) or _element_center(el)
        else:
            c = _element_center(el)
        if not c or c[0] is None or c[1] is None:
            continue
        out.append({
            "name": name[:80],
            "kind": kind or tags.get("place") or tags.get("highway") or tags.get("building") or "place",
            "lon": round(c[0], 7),
            "lat": round(c[1], 7),
        })

    # De-dupe by (name, lon, lat) rounded to ~20m.
    seen = set()
    uniq = []
    for lb in out:
        key = (lb["name"], round(lb["lon"], 4), round(lb["lat"], 4))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(lb)
    return uniq


def geometry_touches_radius(geometry, lat: float, lon: float, radius_m: float) -> bool:
    """True when any vertex of a lon/lat geometry is within the requested radius.

    The Overpass ``around`` and bbox filters are evaluated by the mirror, and a
    mirror is not always to be trusted with them: an out-of-area element set has
    been observed from a public mirror serving stale cached results. Placing
    such an element in the twin would attribute a building or an underground
    asset to the wrong location, several kilometres from the requested area.

    So the requested area is re-checked here against the geometry actually
    returned, and anything wholly outside is dropped. This mirrors Overpass
    ``around`` semantics, which select elements having at least one node in
    range.
    """
    for point in geometry or ():
        if len(point) < 2 or point[0] is None or point[1] is None:
            continue
        if haversine_m(lat, lon, float(point[1]), float(point[0])) <= radius_m:
            return True
    return False


def haversine_m(la1: float, lo1: float, la2: float, lo2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp = math.radians(la2 - la1)
    dl = math.radians(lo2 - lo1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))