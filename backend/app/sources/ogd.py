"""data.gov.in Open Government Data (OGD) source — Government of India.

The OGD platform is operated by the Ministry of Electronics and Information
Technology (MeitY). Access requires a registered API key and a resource id, so
this source stays dormant until both are configured:

    OGD_API_KEY=...            # api.data.gov.in key (register at data.gov.in)
    OGD_RESOURCE_ID=...        # uuid of the dataset resource
    OGD_BASE_URL=https://api.data.gov.in

Rows are mapped to buildings only when the dataset actually carries geometry:
a column holding GeoJSON/WKT/``MultiPolygon`` (or a ``latitude``/``longitude``
pair plus a ``footprint``). A row without geometry is reported as a warning
rather than being turned into a guessed footprint.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.sources.base import AreaData, NoAuthenticSourceError, Provenance, ring_area_m2

OGD_LICENSE = "Open Government Data Licence (OGDL), Government of India — data.gov.in"

_LAT_KEYS = ("latitude", "lat", "y_coord", "y")
_LON_KEYS = ("longitude", "lon", "lng", "long", "x_coord", "x")
_GEOM_KEYS = (
    "geometry",
    "geojson",
    "geo_json",
    "the_geom",
    "footprint",
    "building_footprint",
    "polygon",
    "wkt",
)
_HEIGHT_KEYS = ("height", "height_m", "building_height", "ht", "ht_m")
_FLOOR_KEYS = ("floors", "floor_count", "no_of_floors", "storeys", "stories")
_NAME_KEYS = ("name", "building_name", "structure_name", "house_name")
_TYPE_KEYS = ("building_type", "usage", "type", "category", "occupancy")


def _pick(row: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for key in keys:
        if key in lowered and lowered[key] not in (None, "", "null"):
            return lowered[key]
    return None


def _parse_geometry(value: Any) -> Optional[List[List[float]]]:
    """Return ``[[lon, lat], ...]`` from GeoJSON/WKT, or ``None``."""
    if value in (None, ""):
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{"):
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                return _parse_wkt(text)
        elif text.upper().startswith(("POLYGON", "MULTIPOLYGON")):
            return _parse_wkt(text)
        else:
            return None
    if not isinstance(value, dict):
        return None

    kind = str(value.get("type", "")).lower()
    coords = value.get("coordinates")
    if kind == "feature":
        return _parse_geometry(value.get("geometry"))
    if kind == "polygon":
        return _outer_ring(coords)
    if kind == "multipolygon" and coords:
        return _outer_ring(coords[0])
    return None


def _outer_ring(polygon: Any) -> Optional[List[List[float]]]:
    if not polygon or not isinstance(polygon[0], list) or not polygon[0]:
        return None
    ring = [[float(pt[0]), float(pt[1])] for pt in polygon[0] if isinstance(pt, (list, tuple)) and len(pt) >= 2]
    if len(ring) >= 3 and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring if len(ring) >= 4 else None


def _parse_wkt(text: str) -> Optional[List[List[float]]]:
    import re

    match = re.search(r"POLYGON\s*\(\((.*)\)\)", text, re.IGNORECASE | re.DOTALL)
    body = match.group(1) if match else None
    if body is None:
        match = re.search(r"MULTIPOLYGON\s*\(\(\((.*)\)\)\)", text, re.IGNORECASE | re.DOTALL)
        body = match.group(1) if match else None
    if body is None:
        return None
    pts: List[List[float]] = []
    for chunk in body.split(","):
        parts = chunk.strip().split()
        if len(parts) >= 2:
            try:
                pts.append([float(parts[0]), float(parts[1])])
            except ValueError:
                continue
    if len(pts) >= 3 and pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts if len(pts) >= 4 else None


def _to_float(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None  # drop NaN


class OGDIndiaSource:
    """data.gov.in resource reader (MeitY, Government of India)."""

    name = "data.gov.in"

    def __init__(self) -> None:
        self.api_key = os.getenv("OGD_API_KEY", "").strip()
        self.resource_id = os.getenv("OGD_RESOURCE_ID", "").strip()
        self.base_url = os.getenv("OGD_BASE_URL", "https://api.data.gov.in").rstrip("/")
        self.dataset_name = os.getenv("OGD_DATASET_NAME", "").strip() or f"data.gov.in resource {self.resource_id or 'unset'}"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.resource_id)

    def fetch(self, lat: float, lon: float, radius: int, max_buildings: int = 220) -> AreaData:
        if not self.is_configured:
            raise NoAuthenticSourceError("data.gov.in requires OGD_API_KEY and OGD_RESOURCE_ID")

        url = f"{self.base_url}/resource/{self.resource_id}"
        params = {"api-key": self.api_key, "format": "json", "limit": str(min(1000, max(50, max_buildings * 5)))}
        try:
            resp = httpx.get(url, params=params, timeout=30.0)
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise NoAuthenticSourceError(f"data.gov.in request failed: {exc}") from exc

        if isinstance(body, dict) and body.get("error"):
            raise NoAuthenticSourceError(f"data.gov.in rejected the request: {body['error']}")

        records = body.get("records") or (body.get("result") or {}).get("records") or []
        if not isinstance(records, list) or not records:
            raise NoAuthenticSourceError("data.gov.in returned no records for this resource")

        buildings: List[Dict[str, Any]] = []
        skipped = 0
        for row in records:
            if not isinstance(row, dict):
                continue
            ring = None
            for key in _GEOM_KEYS:
                if key in {str(k).strip().lower() for k in row}:
                    ring = _parse_geometry(row.get(key))
                    if ring:
                        break
            if not ring:
                skipped += 1
                continue
            area = ring_area_m2(ring, lat)
            if not area or area <= 0:
                skipped += 1
                continue
            center = [
                sum(p[0] for p in ring[:-1]) / max(1, len(ring) - 1),
                sum(p[1] for p in ring[:-1]) / max(1, len(ring) - 1),
            ]
            height = _to_float(_pick(row, _HEIGHT_KEYS))
            floors = _to_float(_pick(row, _FLOOR_KEYS))
            buildings.append(
                {
                    "id": str(row.get("id") or _pick(row, ("id",)) or len(buildings) + 1),
                    "name": str(_pick(row, _NAME_KEYS) or f"{self.name} record"),
                    "height_m": round(height, 1) if height else None,
                    "floors": int(floors) if floors else None,
                    "type": str(_pick(row, _TYPE_KEYS) or "tower"),
                    "ring_geo": ring,
                    "center_geo": center,
                    "footprint_area_m2": round(area, 1),
                }
            )
            if len(buildings) >= max_buildings:
                break

        if not buildings:
            raise NoAuthenticSourceError(
                "data.gov.in records for this resource carry no building geometry "
                "(needs a GeoJSON/WKT footprint column)"
            )

        warnings = []
        if skipped:
            warnings.append(f"{skipped} records skipped (no building geometry)")
        return AreaData(
            buildings=buildings,
            labels=[],
            provenance=Provenance(
                provider=self.name,
                dataset=self.dataset_name,
                license=OGD_LICENSE,
                source_url=f"https://www.data.gov.in/resource/{self.resource_id}",
                authoritative=True,
            ),
            warnings=warnings,
        )
