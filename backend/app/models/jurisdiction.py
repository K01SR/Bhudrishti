from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base


class Jurisdiction(Base):
    __tablename__ = "jurisdictions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(50), unique=True, nullable=False, index=True)  # e.g., "MH-THN-AIR-SEC08"
    name = Column(String(200), nullable=False)                         # e.g., "Airoli Sector 8"
    state = Column(String(100), nullable=False, default="Maharashtra")
    district = Column(String(100), nullable=False, default="Thane")
    taluka = Column(String(100), nullable=False, default="Thane")
    village_ward = Column(String(100), nullable=False, default="Ward 08")
    
    # Boundary and center
    center_lat = Column(Float, nullable=False, default=19.1557)
    center_lng = Column(Float, nullable=False, default=72.9984)
    boundary_geojson = Column(JSON, nullable=True)

    # Municipal rules. max_fsi is the permitted FAR/FSI: NULL means no rule is
    # on record for this jurisdiction, which suppresses any FSI verdict.
    max_fsi = Column(Float, nullable=True)
    # Whether the rule (and the boundary above) came from an authentic planning
    # authority record rather than demonstration content.
    provenance_authoritative = Column(Boolean, default=False)
    rule_source = Column(String(200), nullable=True)  # e.g. official DCR/UDCPR citation
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    parcels = relationship("Parcel", back_populates="jurisdiction", cascade="all, delete-orphan")
    users = relationship("User", back_populates="jurisdiction")
