"""Contract for authentic area data providers.

Every building twin the platform renders must be traceable to a real published
dataset. A provider therefore has to return a :class:`Provenance` record next to
the geometry it produces, and it must raise rather than invent data: there is
deliberately no synthetic/fallback path in this package.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol


class NoAuthenticSourceError(RuntimeError):
    """No configured provider could supply real data for the requested area.

    Raised instead of returning generated geometry: an unreachable source is a
    visible outage, never a licence to fabricate buildings.
    """


@dataclass(frozen=True)
class Provenance:
    """Where a payload came from, and whether it is an official publication."""

    provider: str
    dataset: str
    license: str
    source_url: str
    authoritative: bool = False
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "dataset": self.dataset,
            "license": self.license,
            "source_url": self.source_url,
            "authoritative": self.authoritative,
            "retrieved_at": self.retrieved_at,
        }


@dataclass
class AreaData:
    """Buildings + named labels for an area, plus its provenance.

    ``buildings`` entries use the shape consumed by the open-data pipeline:
    ``id``, ``name``, ``height_m`` (may be ``None`` when the source omits it),
    ``floors`` (may be ``None``), ``type``, ``ring_geo`` (``[[lon, lat], ...]``)
    and ``center_geo``.
    """

    buildings: List[Dict[str, Any]]
    labels: List[Dict[str, Any]]
    provenance: Provenance
    warnings: List[str] = field(default_factory=list)
    # Whose names these are, when they did not come from the footprint provider.
    # A footprint source and a place-name source are different datasets: GlobalML
    # is the densest footprint source for India and returns no names at all, so
    # the chain may fill them from OpenStreetMap. Without this field a consumer
    # would attribute the names to whichever provider supplied the footprints.
    label_provenance: Optional[Dict[str, Any]] = None

    @property
    def source(self) -> str:
        return self.provenance.provider


class AreaSource(Protocol):
    """A publishable dataset that can describe buildings for a coordinate."""

    name: str

    @property
    def is_configured(self) -> bool:
        """True when credentials/endpoint needed by this source are present."""

    def fetch(self, lat: float, lon: float, radius: int, max_buildings: int = 220) -> AreaData:
        """Return real data, or raise :class:`NoAuthenticSourceError`."""


def ring_area_m2(ring: List[List[float]], lat_ref: float) -> Optional[float]:
    """Planar area of a ``[[lon, lat], ...]`` ring in m² (equirectangular)."""
    if not ring or len(ring) < 3:
        return None
    kx = 111320.0 * abs(_cos(lat_ref))
    ky = 110540.0
    total = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = (ring[i][0] - ring[0][0]) * kx, (ring[i][1] - ring[0][1]) * ky
        x2, y2 = (ring[i + 1][0] - ring[0][0]) * kx, (ring[i + 1][1] - ring[0][1]) * ky
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _cos(value: float) -> float:
    import math

    return math.cos(math.radians(value))
