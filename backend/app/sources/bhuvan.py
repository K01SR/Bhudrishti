"""ISRO/NRSA Bhuvan vector source (Government of India).

Bhuvan (by the National Remote Sensing Centre, ISRO) publishes government
imagery and, for some layers, vector feature services. Building footprints are
served through an OGC Web Feature Service, so this source issues a real
``GetFeature`` request constrained to the requested bounding box and reads back
GML:

    BHUVAN_WFS_URL=https://<host>/geoserver/wfs        # e.g. a state/ULB footprint layer
    BHUVAN_WFS_LAYER=gov:building_footprints
    BHUVAN_WFS_NAMESPACE=gov
    BHUVAN_DATASET_NAME=Bhuvan building footprints (<layer>)

Without those settings the source reports itself unconfigured. Imagery-only
Bhuvan deployments have no footprint layer and will correctly stay dormant
rather than fall back to invented geometry.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.sources.base import AreaData, NoAuthenticSourceError, Provenance, ring_area_m2

BHUVAN_LICENSE = "Bhuvan (NRSC/ISRO), Government of India — terms of use apply"


def _bbox(lat: float, lon: float, radius: int) -> Tuple[float, float, float, float]:
    """Approximate WGS84 bounding box for a radius in metres (envelope bbox)."""
    import math

    dlat = radius / 110540.0
    dlon = radius / (111320.0 * max(0.05, abs(math.cos(math.radians(lat)))))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_gml(coordinates_text: str) -> List[List[float]]:
    """Parse a gml:coordinates string into a list of (lon, lat) pairs."""
    pts: List[List[float]] = []
    for token in coordinates_text.split():
        if "," not in token:
            continue
        a, b = token.split(",", 1)
        try:
            pts.append([float(a), float(b)])
        except ValueError:
            continue
    return pts


def _extract_rings(xml_text: str) -> List[List[List[float]]]:
    """Pull every Polygon exterior ring out of a WFS GML response."""
    root = ET.fromstring(xml_text)
    rings: List[List[List[float]]] = []
    for polygon in root.iter():
        if _local_name(polygon.tag) != "Polygon":
            continue
        for ring in polygon.iter():
            if _local_name(ring.tag) != "LinearRing":
                continue
            pts: List[List[float]] = []
            for member in ring:
                if _local_name(member.tag) != "posList" and _local_name(member.tag) != "coordinates":
                    continue
                raw = (member.text or "").strip()
                if _local_name(member.tag) == "posList":
                    nums = raw.split()
                    pts += [[float(nums[i]), float(nums[i + 1])] for i in range(0, len(nums) - 1, 2)]
                else:
                    pts += _parse_gml(raw)
            if len(pts) >= 4:
                if pts[0] != pts[-1]:
                    pts.append(pts[0])
                rings.append(pts)
    return rings


def _extract_props(feature: ET.Element) -> Dict[str, str]:
    props: Dict[str, str] = {}
    for child in feature:
        name = _local_name(child.tag)
        if name in {"geometry", "boundedBy", "polygon", "Polygon", "multiSurface", "MultiSurface"}:
            continue
        value = (child.text or "").strip()
        if value:
            props[name] = value
    return props


class BhuvanWFSVectorSource:
    """ISRO/NRSA Bhuvan footprint layer read through OGC WFS."""

    name = "bhuvan"

    def __init__(self) -> None:
        self.wfs_url = os.getenv("BHUVAN_WFS_URL", "").strip()
        self.layer = os.getenv("BHUVAN_WFS_LAYER", "").strip()
        self.namespace = os.getenv("BHUVAN_WFS_NAMESPACE", "").strip()
        self.dataset_name = os.getenv("BHUVAN_DATASET_NAME", "").strip() or f"Bhuvan vector layer {self.layer or 'unset'}"
        self.timeout = float(os.getenv("BHUVAN_TIMEOUT_S", "45"))

    @property
    def is_configured(self) -> bool:
        return bool(self.wfs_url and self.layer)

    def _type_name(self) -> str:
        return f"{self.namespace}:{self.layer}" if self.namespace else self.layer

    def fetch(self, lat: float, lon: float, radius: int, max_buildings: int = 220) -> AreaData:
        if not self.is_configured:
            raise NoAuthenticSourceError("Bhuvan vector source requires BHUVAN_WFS_URL and BHUVAN_WFS_LAYER")

        minx, miny, maxx, maxy = _bbox(lat, lon, radius)
        params = {
            "service": "WFS",
            "version": "1.1.0",
            "request": "GetFeature",
            "typeName": self._type_name(),
            "maxFeatures": str(max_buildings),
            "bbox": f"{minx},{miny},{maxx},{maxy},EPSG:4326",
        }
        try:
            resp = httpx.get(self.wfs_url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            text = resp.text
        except Exception as exc:  # noqa: BLE001
            raise NoAuthenticSourceError(f"Bhuvan WFS request failed: {exc}") from exc

        if "ServiceException" in text or "<ows:ExceptionReport" in text:
            raise NoAuthenticSourceError(f"Bhuvan WFS returned a service exception: {text[:180]}")

        try:
            rings = _extract_rings(text)
        except ET.ParseError as exc:
            raise NoAuthenticSourceError(f"Bhuvan WFS response is not parseable GML: {exc}") from exc

        if not rings:
            raise NoAuthenticSourceError("Bhuvan WFS layer returned no footprints for this area")

        buildings: List[Dict[str, Any]] = []
        labels: List[Dict[str, Any]] = []
        for idx, ring in enumerate(rings[:max_buildings], start=1):
            area = ring_area_m2(ring, lat)
            if not area or area <= 0:
                continue
            center = [
                sum(p[0] for p in ring[:-1]) / max(1, len(ring) - 1),
                sum(p[1] for p in ring[:-1]) / max(1, len(ring) - 1),
            ]
            buildings.append(
                {
                    "id": f"BHV-{idx:05d}",
                    "name": f"Bhuvan footprint {idx}",
                    "height_m": None,
                    "floors": None,
                    "type": "tower",
                    "ring_geo": ring,
                    "center_geo": center,
                    "footprint_area_m2": round(area, 1),
                }
            )

        if not buildings:
            raise NoAuthenticSourceError("Bhuvan WFS footprints had zero area in this area")

        return AreaData(
            buildings=buildings,
            labels=labels,
            provenance=Provenance(
                provider=self.name,
                dataset=self.dataset_name,
                license=BHUVAN_LICENSE,
                source_url=f"https://bhuvan.nrsc.gov.in/ ({self._type_name()})",
                authoritative=True,
            ),
            warnings=["Bhuvan footprints carry no height or floor data; massing is footprint-only"],
        )
