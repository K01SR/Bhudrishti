from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, JSON, Boolean, Text
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from app.core.database import Base


class Parcel(Base):
    __tablename__ = "parcels"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ulpin = Column(String(14), unique=True, nullable=False, index=True)  # Official 14-char ULPIN
    survey_number = Column(String(100), nullable=True)
    jurisdiction_id = Column(String(36), ForeignKey("jurisdictions.id"), nullable=False)
    
    # 2D Geometry & Boundary
    polygon_geojson = Column(JSON, nullable=False)
    boundary_coordinates = Column(JSON, nullable=True)
    document_area_m2 = Column(Float, nullable=False)
    calculated_area_m2 = Column(Float, nullable=False)
    gis_area_m2 = Column(Float, nullable=True)

    status = Column(String(50), default="ACTIVE")  # ACTIVE, PENDING_SURVEY, CONFLICT
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Provenance: which published dataset this record came from, and whether it
    # is an authentic cadastral record or generated demonstration content.
    # Compliance verdicts (FSI/FAR) are only issued for authentic records.
    data_provenance = Column(String(50), default="demo-generated")  # demo-generated | openstreetmap | data.gov.in | bhuvan | survey
    provenance_authoritative = Column(Boolean, default=False)
    provenance_detail = Column(JSON, nullable=True)

    # Address and locality as claimed by the submitter (town/ward strings, not
    # geocoded). A parcel row created from a builder form carries these before
    # any survey or authority publishes its own.
    address = Column(String(300), nullable=True)
    locality = Column(String(200), nullable=True)

    # PostGIS 2D boundary (real geometry, projected UTM zone 43N)
    geom = Column(Geometry("POLYGON", srid=32643), nullable=True)
    geom_hash = Column(String(64), nullable=True, index=True)

    # Relationships
    jurisdiction = relationship("Jurisdiction", back_populates="parcels")
    structures = relationship("Structure", back_populates="parcel", cascade="all, delete-orphan")
    spatial_units = relationship("SpatialUnit", back_populates="parcel", cascade="all, delete-orphan")
    submissions = relationship("Submission", back_populates="parcel")
    verification_cases = relationship("VerificationCase", back_populates="parcel")


class Structure(Base):
    __tablename__ = "structures"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parcel_id = Column(String(36), ForeignKey("parcels.id"), nullable=False)
    building_code = Column(String(50), nullable=False)  # e.g., "B-17"
    name = Column(String(200), nullable=False)
    structure_type = Column(String(50), default="RESIDENTIAL_COMMERCIAL")
    
    # Footprint & Height
    footprint_geojson = Column(JSON, nullable=False)
    ground_elevation_z = Column(Float, default=0.0)
    height_m = Column(Float, nullable=False)
    floors_count = Column(Integer, nullable=False, default=1)
    basements_count = Column(Integer, nullable=False, default=0)
    
    total_built_up_area_m2 = Column(Float, nullable=False, default=0.0)
    calculated_fsi = Column(Float, nullable=True)  # only set when a permitted-FSI rule exists
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Provenance of the measured massing (see Parcel.data_provenance).
    data_provenance = Column(String(50), default="demo-generated")
    provenance_authoritative = Column(Boolean, default=False)
    height_basis = Column(String(50), default="unknown")  # surveyed | inferred_from_tags | unknown

    # PostGIS 3D solid (PolyhedralSurfaceZ in projected UTM zone 43N)
    geom_3d = Column(Geometry("POLYHEDRALSURFACEZ", srid=32643), nullable=True)
    observed_height_m = Column(Float, nullable=True)      # VC-X LiDAR observed height
    extraction_source = Column(String(200), nullable=True)  # run_hash / dataset provenance

    parcel = relationship("Parcel", back_populates="structures")
    levels = relationship("Level", back_populates="structure", cascade="all, delete-orphan", order_by="Level.min_z")
    units = relationship("Unit", back_populates="structure", cascade="all, delete-orphan")


class Level(Base):
    __tablename__ = "levels"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    structure_id = Column(String(36), ForeignKey("structures.id"), nullable=False)
    level_code = Column(String(20), nullable=False)   # "B1", "G", "L01", "L02", ..., "L05"
    floor_number = Column(Integer, nullable=False)    # -1, 0, 1, 2, ...
    min_z = Column(Float, nullable=False)
    max_z = Column(Float, nullable=False)
    height_m = Column(Float, nullable=False)
    level_type = Column(String(50), default="HABITABLE")  # BASEMENT, GROUND, HABITABLE, ROOFTOP
    # What the submitter called and used this floor for. Load-bearing for the
    # detail view and 3D labels; they are claims, not a survey's names.
    name = Column(String(200), nullable=True)
    use = Column(String(100), nullable=True)
    boundary_geojson = Column(JSON, nullable=True)
    geom_3d = Column(Geometry("POLYHEDRALSURFACEZ", srid=32643), nullable=True)

    structure = relationship("Structure", back_populates="levels")
    units = relationship("Unit", back_populates="level", cascade="all, delete-orphan")


class Unit(Base):
    __tablename__ = "units"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    structure_id = Column(String(36), ForeignKey("structures.id"), nullable=False)
    level_id = Column(String(36), ForeignKey("levels.id"), nullable=False)
    
    unit_number = Column(String(50), nullable=False)  # "101", "201", "P01"
    proposed_3d_id = Column(String(100), unique=True, nullable=False, index=True)
    unit_type = Column(String(50), default="U")  # U = Unit, P = Parking, X = Utility
    
    # 3D Elevation bounds
    min_z = Column(Float, nullable=False)
    max_z = Column(Float, nullable=False)
    carpet_area_m2 = Column(Float, nullable=False)
    built_up_area_m2 = Column(Float, nullable=False)
    volume_m3 = Column(Float, nullable=False)
    
    # 2D & 3D Geometry representations
    footprint_geojson = Column(JSON, nullable=False)
    mesh_geometry_3d = Column(JSON, nullable=True)  # Vertices & faces for Three.js
    geom_3d = Column(Geometry("POLYHEDRALSURFACEZ", srid=32643), nullable=True)
    
    status = Column(String(50), default="DRAFT")  # DRAFT, SUBMITTED, GENERATED, NEEDS_REVIEW, APPROVED, REJECTED
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    structure = relationship("Structure", back_populates="units")
    level = relationship("Level", back_populates="units")
    rights = relationship("Right", back_populates="unit", cascade="all, delete-orphan")


class SpatialUnit(Base):
    __tablename__ = "spatial_units"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parcel_id = Column(String(36), ForeignKey("parcels.id"), nullable=False)
    code = Column(String(100), nullable=False)
    proposed_3d_id = Column(String(100), unique=True, nullable=False, index=True)
    
    type_code = Column(String(10), nullable=False)  # X (Underground), E (Elevated), A (Air-right)
    description = Column(String(255), nullable=False)
    min_z = Column(Float, nullable=False)
    max_z = Column(Float, nullable=False)
    geometry_3d = Column(JSON, nullable=False)  # Lines / extruded prisms / pipes
    has_clash = Column(Boolean, default=False)
    clash_details = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    parcel = relationship("Parcel", back_populates="spatial_units")
