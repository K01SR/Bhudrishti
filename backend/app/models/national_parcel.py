from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Float, DateTime, JSON, UniqueConstraint
from geoalchemy2 import Geometry
from app.core.database import Base


class NationalParcel(Base):
    """Deterministic synthetic parcel inside a real admin boundary.

    Every NationalParcel carries a georeferenced EPSG:4326 polygon and a
    14-char ULPIN derived from its vertices (``national.py`` / Bhu-Aadhaar
    aligned). Level linkage: VILLAGE/TALUKA/DISTRICT boundary_code is kept so
    parcel density can be scaled by jurisdiction size.
    """

    __tablename__ = "national_parcels"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ulpin = Column(String(14), unique=True, nullable=False, index=True)  # derived 14-char national ULPIN
    survey_number = Column(String(60), nullable=True)
    boundary_code = Column(String(120), nullable=False, index=True)  # admin_boundaries.code (village/taluka/district)
    state_code = Column(String(12), nullable=False, index=True)
    district_code = Column(String(80), nullable=True)

    geom = Column(Geometry("POLYGON", srid=4326), nullable=True)
    centroid_lat = Column(Float, nullable=True)
    centroid_lng = Column(Float, nullable=True)
    area_m2 = Column(Float, nullable=True)

    derivation = Column(JSON, nullable=True)  # national.py metadata (method, cell_key, centroid)
    zonal_class = Column(String(30), nullable=True)  # e.g. RESIDENTIAL, AGRI, COMMERCIAL

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("ulpin", name="uq_national_parcels_ulpin"),
    )

    def __repr__(self) -> str:
        return f"<NationalParcel {self.ulpin} in {self.boundary_code}>"