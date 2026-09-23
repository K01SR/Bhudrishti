"""Turn a real place name into a real coordinate, using OpenStreetMap Nominatim.

Why this exists
---------------
The LGD directory knows that "Airoli" is a village in Thane district, Maharashtra
with code 943726, but it publishes no latitude or longitude. To put a place on a
map, fly a camera to it, or pull building footprints around it, something has to
supply a position. Nominatim is that something: the official geocoder over
OpenStreetMap data, free and credential-free, which makes the whole 677,673-row
directory addressable without a paid gazetteer.

The honesty problem, and how it is handled
------------------------------------------
A geocoded point is *derived*, not surveyed. Nominatim returns the centroid of a
matched feature, and a village centroid is wherever the mapper put it. Presenting
it as a measured position would overstate it, so every result here is tagged
``derived`` and carries:

* ``match_type``  - what Nominatim actually matched (node, relation, ward…)
* ``importance``  - Nominatim's own confidence in the match
* ``display_name`` - the full string it resolved to, so a human can audit it
* ``query``       - exactly what was sent, including the district and state
  context used to disambiguate

Disambiguation is the part that decides whether this is useful or wrong. India
has several villages called "Airoli" and more that share a name with a taluka or
a district, so the query is built hierarchically - village, sub-district,
district, state - and progressively relaxed until something matches. The
``strategy`` field records which level of specificity produced the answer.

Usage limits
------------
Nominatim's public instance allows one request per second, so requests are
serialised, rate-limited and cached on disk. Answers are cached for a long time
because a village centroid does not move between releases; failures are cached
briefly so a typo cannot become a hot retry loop.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.sources.base import NoAuthenticSourceError, Provenance

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_LICENSE = "Open Database License (ODbL) 1.0 - (c) OpenStreetMap contributors"
NOMINATIM_DATASET = "OpenStreetMap / Nominatim geocoder"
USER_AGENT = os.getenv(
    "NOMINATIM_USER_AGENT",
    "BhuDrishti3D/1.0 (3D cadastral prototype; LGD place geocoding)",
)

# One request per second, per the public Nominatim usage policy.
_MIN_INTERVAL_S = 1.05
_HIT_TTL_S = 180 * 24 * 3600
_MISS_TTL_S = 600
_TIMEOUT_S = 20

_lock = threading.Lock()
_last_request = 0.0


def _cache_dir() -> Path:
    base = (
        Path("/app/data")
        if Path("/app/data").is_dir()
        else Path(__file__).resolve().parents[3].parent / "data"
    )
    path = base / "geocode_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_key(query: str) -> Path:
    import hashlib

    digest = hashlib.sha1(query.lower().encode("utf-8")).hexdigest()
    return _cache_dir() / f"{digest}.json"


def _read_cache(query: str) -> Optional[Any]:
    path = _cache_key(query)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    age = time.time() - payload.get("stored_at", 0)
    ttl = _HIT_TTL_S if payload.get("value") else _MISS_TTL_S
    return payload.get("value") if age < ttl else None


def _write_cache(query: str, value: Any) -> None:
    try:
        _cache_key(query).write_text(
            json.dumps({"stored_at": time.time(), "value": value}), encoding="utf-8"
        )
    except OSError:
        pass


def _throttle() -> None:
    """Hold the public-instance rate limit of one request per second."""
    global _last_request
    with _lock:
        wait = _MIN_INTERVAL_S - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.time()


def _get_json(url: str) -> List[Dict[str, Any]]:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    _throttle()
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:  # noqa: S310 - fixed host
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        raise NoAuthenticSourceError(f"Nominatim unavailable: {exc}") from exc


def clean_place(name: Optional[str]) -> str:
    """Strip the decorations that stop a gazetteer name matching.

    Census and postal suffixes are removed because the gazetteer files a place
    under its bare name ("Nerul", not "Nerul (Ct)"). Letters in any script are
    preserved: Indian local-language names are indexed too, and reducing them to
    ASCII would throw away half the directory.
    """
    text = unicodedata.normalize("NFKC", (name or "")).strip()
    text = re.sub(
        r"\s*\(\s*(?:ct|cty|city|ori|trib|rly|nai|maha|proj|blk)\.?\s*\)", " ", text, flags=re.I
    )
    # Preserve letters in every script. Python's ``\w`` is not enough: it drops
    # Devanagari vowel signs, which ``str.isalpha`` also reports as
    # non-letters, so a naive ASCII filter silently shreds half of every
    # local-language place name in the directory.
    text = "".join(ch if (ch.isalnum() or unicodedata.category(ch).startswith("M")) else " " for ch in text)
    text = re.sub(r"[\d_]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _provenance(strategy: str) -> Dict[str, Any]:
    return Provenance(
        provider="nominatim",
        dataset=NOMINATIM_DATASET,
        license=NOMINATIM_LICENSE,
        source_url="https://nominatim.openstreetmap.org",
        authoritative=False,  # community-mapped, and the point is a centroid
    ).as_dict() | {"geocoding_strategy": strategy, "geocoded": True}


def _hit_to_result(hit: Dict[str, Any], query: str, strategy: str) -> Dict[str, Any]:
    lat = float(hit["lat"])
    lon = float(hit["lon"])
    osm_type = hit.get("type") or hit.get("osm_type") or hit.get("class")
    osm_class = (hit.get("class") or hit.get("category") or "").lower()
    # Tell the caller whether this point describes the settlement or merely
    # shares its name. A railway station called "Nerul" is close enough to be
    # useful, but a UI should not present it as the village extent.
    is_settlement = osm_class in _PLACE_CLASSES and (hit.get("type") or "").lower() in _PLACE_TYPES
    return {
        "found": True,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "display_name": hit.get("display_name"),
        "osm_type": osm_type,
        "osm_id": hit.get("osm_id"),
        "osm_class": hit.get("class") or hit.get("category"),
        "importance": hit.get("importance"),
        "bounding_box": hit.get("boundingbox"),
        "is_settlement": is_settlement,
        "match_quality": "settlement" if is_settlement else "incidental",
        "query": query,
        "strategy": strategy,
        "provenance": _provenance(strategy),
    }


# A village name will also match a railway station, a bus stop or a hospital
# that happens to share it, and those points sit on the edge of the settlement
# rather than in it. Prefer the feature that describes the place itself.
_PLACE_CLASSES = ("boundary", "place", "landuse", "locality")
_PLACE_TYPES = (
    "village", "town", "hamlet", "suburb", "neighbourhood", "quarter",
    "locality", "city", "municipality", "administrative",
)


def _rank_hit(hit: Dict[str, Any]) -> tuple:
    """Sort key: lower is better. Settlements first, incidental features last."""
    osm_class = (hit.get("class") or hit.get("category") or "").lower()
    osm_type = (hit.get("type") or hit.get("osm_type") or "").lower()
    class_rank = _PLACE_CLASSES.index(osm_class) if osm_class in _PLACE_CLASSES else len(_PLACE_CLASSES)
    type_rank = _PLACE_TYPES.index(osm_type) if osm_type in _PLACE_TYPES else len(_PLACE_TYPES)
    # A settlement match at a looser specificity still beats a station match at
    # a tighter one, so class/type outrank Nominatim's own importance score.
    return (class_rank, type_rank, -(hit.get("importance") or 0.0))


def geocode_place(
    village_name: str,
    district_name: Optional[str] = None,
    subdistrict_name: Optional[str] = None,
    state_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Locate one place, relaxing the query until it resolves.

    Strategies are tried in order of specificity, so a hit at the first level
    is a hit that actually used the district and state to disambiguate. A hit
    from the loosest level is a last resort and is flagged as such.
    """
    village = clean_place(village_name)
    district = clean_place(district_name)
    subdistrict = clean_place(subdistrict_name)
    state = clean_place(state_name)
    if not village:
        return {"found": False, "query": "", "strategy": "empty", "provenance": _provenance("empty")}

    attempts: List[tuple[str, str]] = []
    if village and district and state:
        if subdistrict:
            attempts.append(
                (f"{village}, {subdistrict}, {district}, {state}, India", "village+subdistrict+district+state")
            )
        attempts.append((f"{village}, {district}, {state}, India", "village+district+state"))
    if village and state:
        attempts.append((f"{village}, {state}, India", "village+state"))
    if village:
        attempts.append((f"{village}, India", "village+country"))
        attempts.append((village, "village-only"))

    seen: set[str] = set()
    for query, strategy in attempts:
        if query in seen:
            continue
        seen.add(query)
        cached = _read_cache(query)
        if cached is not None:
            if cached.get("found"):
                return cached | {"strategy": cached.get("strategy", strategy)}
            continue
        params = urllib.parse.urlencode(
            {
                "q": query,
                "format": "jsonv2",
                "limit": 8,
                "addressdetails": 1,
                "countrycodes": "in",
                # Ask for settlement features only, but do not rely on it: the
                # filter still lets through incidental features, which is why
                # the results are re-ranked below.
                "featuretype": "settlement",
            }
        )
        try:
            hits = _get_json(f"{NOMINATIM_URL}?{params}")
        except NoAuthenticSourceError:
            raise
        if hits:
            best = sorted(hits, key=_rank_hit)[0]
            result = _hit_to_result(best, query, strategy)
            _write_cache(query, result)
            return result
        _write_cache(query, {"found": False, "query": query, "strategy": strategy})

    return {
        "found": False,
        "query": attempts[-1][1] if attempts else "",
        "strategy": "unresolved",
        "provenance": _provenance("unresolved"),
        "note": "no OpenStreetMap feature matched; place stays unresolved rather than guessed",
    }
