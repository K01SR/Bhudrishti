"""OpenStreetMap area source (live, no credentials required).

OpenStreetMap is open-licensed community data, not an official government
publication, so its provenance is marked ``authoritative=False``. It is the
default provider because it is the only public source that reliably serves
building footprints for arbitrary coordinates.
"""
from __future__ import annotations

from typing import Any, Dict

from app.opendata.overpass import fetch_osm_area
from app.sources.base import AreaData, NoAuthenticSourceError, Provenance, ring_area_m2

OSM_LICENSE = "Open Database License (ODbL) 1.0 - © OpenStreetMap contributors"


class OpenStreetMapSource:
    name = "openstreetmap"

    @property
    def is_configured(self) -> bool:
        return True

    def fetch(self, lat: float, lon: float, radius: int, max_buildings: int = 220) -> AreaData:
        try:
            raw: Dict[str, Any] = fetch_osm_area(lat, lon, radius, max_buildings=max_buildings)
        except Exception as exc:  # noqa: BLE001 - surfaced as a source outage
            raise NoAuthenticSourceError(f"OpenStreetMap unavailable: {exc}") from exc

        if not raw.get("buildings"):
            raise NoAuthenticSourceError("OpenStreetMap returned no building footprints for this area")

        # Overpass does not report areas, so derive the footprint area from the
        # ring (every other provider returns it, so the contract stays uniform).
        buildings = []
        for b in raw["buildings"]:
            enriched = dict(b)
            enriched.setdefault("footprint_area_m2", None)
            if enriched["footprint_area_m2"] is None:
                area = ring_area_m2(b.get("ring_geo") or [], lat)
                enriched["footprint_area_m2"] = round(area, 1) if area else None
            buildings.append(enriched)

        warnings = []
        if not raw.get("labels"):
            warnings.append("no named places returned for this area")
        missing_height = sum(1 for b in buildings if b.get("height_m") is None)
        if missing_height:
            warnings.append(f"{missing_height} footprints carry no surveyed height; floor counts are inferred")

        return AreaData(
            buildings=buildings,
            labels=raw.get("labels", []),
            provenance=Provenance(
                provider=self.name,
                dataset="OpenStreetMap building footprints + named places (Overpass API)",
                license=OSM_LICENSE,
                source_url=f"https://www.openstreetmap.org/#map=17/{lat}/{lon}",
                authoritative=False,
            ),
            warnings=warnings,
        )
