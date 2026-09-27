"""Provider chain for area data.

Order matters: government publications are preferred, then the satellite-derived
GlobalML release, and OpenStreetMap last because it is community-contributed
rather than official. The chain is configurable through ``OPENDATA_SOURCES``
(comma separated), defaulting to
``bhuvan,data.gov.in,globalml,openstreetmap`` — dormant providers are skipped,
so with no government credentials configured the chain resolves to GlobalML or
OpenStreetMap.
"""
from __future__ import annotations

import os
from typing import List, Optional

from dataclasses import replace

from app.sources.base import AreaData, AreaSource, NoAuthenticSourceError
from app.sources.bhuvan import BhuvanWFSVectorSource
from app.sources.globalml import GlobalMLSource
from app.sources.ogd import OGDIndiaSource
from app.sources.openstreetmap import OpenStreetMapSource

_PROVIDERS = {
    "bhuvan": BhuvanWFSVectorSource,
    "data.gov.in": OGDIndiaSource,
    "globalml": GlobalMLSource,
    "openstreetmap": OpenStreetMapSource,
}

DEFAULT_ORDER = "bhuvan,data.gov.in,globalml,openstreetmap"


def provider_order() -> List[str]:
    raw = os.getenv("OPENDATA_SOURCES", DEFAULT_ORDER)
    names = [n.strip() for n in raw.split(",") if n.strip()]
    unknown = [n for n in names if n not in _PROVIDERS]
    if unknown:
        raise ValueError(f"unknown OPENDATA_SOURCES entries: {', '.join(unknown)}")
    return names


def get_providers() -> List[AreaSource]:
    """Instantiate the configured, ready-to-use providers in priority order."""
    ready: List[AreaSource] = []
    for name in provider_order():
        provider = _PROVIDERS[name]()
        if provider.is_configured:
            ready.append(provider)
    return ready


def unconfigured_providers() -> List[str]:
    return [n for n in provider_order() if not _PROVIDERS[n]().is_configured]


def _labels_from_openstreetmap(
    lat: float, lon: float, radius: int, problems: List[str]
):
    """Place names for an area, from OpenStreetMap specifically.

    Footprints and place names are different datasets, and a provider that wins
    the footprint race is not thereby able to supply names. GlobalML is the
    common case: it is the densest footprint source for India, so it usually
    wins, and it returns ``labels=[]`` unconditionally because it is satellite
    footprint detection with no notion of a street or a shop. Areas served by it
    therefore came back with 220 buildings and not one name, which left the
    whole map unselectable by name and gave the caller nothing to place.

    So names are gathered from OpenStreetMap whatever supplied the footprints,
    and the response records that they came from there. This is a fallback for
    missing data, not a replacement: a provider that does return labels keeps
    them, because those are authoritative for the footprints it just returned.
    """
    from app.opendata.overpass import fetch_osm_labels
    from app.sources.base import Provenance
    from app.sources.openstreetmap import OSM_LICENSE

    try:
        # Label-only: the footprints already came from another provider, so
        # asking Overpass for them again would spend a large round-trip on data
        # we would throw away and leave the names to race the leftover budget.
        labels = fetch_osm_labels(lat, lon, radius)
    except Exception as exc:  # noqa: BLE001 - labels are an enrichment, never fatal
        problems.append(f"openstreetmap labels: {type(exc).__name__}: {exc}")
        return None, None

    provenance = Provenance(
        provider="openstreetmap",
        dataset="OpenStreetMap named places (Overpass API)",
        license=OSM_LICENSE,
        source_url=f"https://www.openstreetmap.org/#map=17/{lat}/{lon}",
        authoritative=False,
    )
    return labels, provenance


def fetch_area(lat: float, lon: float, radius: int, max_buildings: int = 220) -> AreaData:
    """Return real data from the first provider that can serve the area.

    Raises :class:`NoAuthenticSourceError` when nothing is reachable or nothing
    is configured. Callers must surface that as an outage — never substitute
    generated geometry.

    A provider that returns footprints but no names is topped up from
    OpenStreetMap, because "no names" is a gap in that provider's coverage
    rather than a fact about the area. See :func:`_labels_from_openstreetmap`.
    """
    problems = []
    for provider in get_providers():
        try:
            area = provider.fetch(lat, lon, radius, max_buildings)
        except NoAuthenticSourceError as exc:
            problems.append(f"{provider.name}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 - a broken provider must not kill the chain
            problems.append(f"{provider.name}: {type(exc).__name__}: {exc}")
            continue

        if area.labels:
            return area

        labels, label_prov = _labels_from_openstreetmap(lat, lon, radius, problems)
        if not labels:
            # No names from anywhere. The footprints still stand on their own, but
            # the reason has to travel with them: this call is an Overpass
            # round-trip behind the same 5s politeness gap, so it fails whenever
            # the provider is throttling, and "0 labels" is otherwise
            # indistinguishable from an area that genuinely has no named places.
            reason = (
                "; ".join(problems[-1:]) if problems else "OpenStreetMap returned no named places here"
            )
            return replace(
                area,
                warnings=[*area.warnings, f"no place names available: {reason}"],
            )
        return replace(
            area,
            labels=labels,
            warnings=[
                *area.warnings,
                f"No place names in {provider.name}; names taken from OpenStreetMap.",
            ],
            # Recorded so a consumer can tell whose names these are.
            label_provenance=label_prov.as_dict() if label_prov else None,
        )

    detail = "; ".join(problems) if problems else "no provider is configured"
    raise NoAuthenticSourceError(
        f"No authentic building source available ({detail}). Configure OPENDATA_SOURCES "
        f"with a reachable provider; no synthetic geometry is generated."
    )
