from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Float, DateTime, JSON, Integer
from geoalchemy2 import Geometry
from app.core.database import Base


class AdminBoundary(Base):
    """Administrative boundary node for the national jurisdiction hierarchy.

    Levels: STATE -> DISTRICT -> TALUKA -> VILLAGE (WGS84 / EPSG:4326).

    Hierarchy codes follow a dashed path, e.g. ``IN-MH`` -> ``IN-MH-THN`` ->
    ``IN-MH-THN-AIR-S8`` so the canonical 14-char ULPIN engine can consume
    them without extra lookups.
    """

    __tablename__ = "admin_boundaries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(120), unique=True, nullable=False, index=True)  # dashed hierarchy path
    name = Column(String(200), nullable=False)
    level = Column(String(20), nullable=False, index=True)  # STATE / DISTRICT / TALUKA / VILLAGE
    parent_code = Column(String(120), nullable=True, index=True)  # code of parent level

    # State / District / Taluka / Village codes (for flat joins & ULPIN derivation)
    state_code = Column(String(12), nullable=False, index=True)
    district_code = Column(String(80), nullable=True)
    taluka_code = Column(String(120), nullable=True)
    village_code = Column(String(120), nullable=True)

    # Source & provenance
    source = Column(String(100), nullable=True, default="geoboundaries")
    source_ref = Column(String(200), nullable=True)

    # Geometry (EPSG:4326, WGS84) + derived stats
    geom = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
    centroid_lat = Column(Float, nullable=True)
    centroid_lng = Column(Float, nullable=True)
    area_km2 = Column(Float, nullable=True)

    # Optional census / governance metadata
    population_estimate = Column(Integer, nullable=True)
    extra_meta = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<AdminBoundary {self.code} {self.level} {self.name}>"