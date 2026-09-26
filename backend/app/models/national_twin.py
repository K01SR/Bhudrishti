from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, UniqueConstraint, Text
from geoalchemy2 import Geometry
from app.core.database import Base


class NationalTwin(Base):
    """Persisted 3D digital twin for a national parcel.

    Built by extruding the parcel geometry with statutory NBC 2016 setbacks
    (converted into the parcel's own UTM metre frame), then persisted with the
    footprint transformed back to georeferenced EPSG:4326 so tiles and
    visualization can consume it directly. Mirrors full 3D-ULPIN minting.
    """

    __tablename__ = "national_twins"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ulpin = Column(String(14), nullable=False, index=True)
    boundary_code = Column(String(120), nullable=False, index=True)
    state_code = Column(String(12), nullable=True)
    survey_number = Column(String(60), nullable=True)

    structure_code = Column(String(50), nullable=False)  # e.g. B-101
    name = Column(String(200), nullable=True)
    typology = Column(String(30), nullable=True)
    structure_type = Column(String(50), nullable=True)

    # footprint (georeferenced 4326)
    footprint_polygon = Column(Geometry("POLYGON", srid=4326), nullable=True)
    footprint_polygon_geojson = Column(JSON, nullable=True)

    # metrics
    plot_area_m2 = Column(Float, nullable=True)
    setback_m = Column(Float, nullable=True)
    buildable_area_m2 = Column(Float, nullable=True)
    footprint_area_m2 = Column(Float, nullable=True)
    floors = Column(Integer, nullable=True)
    floor_height_m = Column(Float, nullable=True)
    height_m = Column(Float, nullable=True)
    built_up_area_m2 = Column(Float, nullable=True)
    fsi = Column(Float, nullable=True)
    fsi_status = Column(String(30), nullable=True)
    # Why fsi/fsi_status are null. A compliance verdict is only meaningful over
    # surveyed geometry, so a twin built from a generated parcel must carry the
    # reason it has no verdict rather than a plausible-looking PASS/EXCEEDED.
    fsi_status_reason = Column(String(200), nullable=True)
    # geometry_basis / authoritative record whether the shape is real. Set to
    # 'modelled_from_synthetic_parcel' + authoritative=false for generated rows.
    provenance = Column(JSON, nullable=True)

    # minting
    proposed_3d_id = Column(String(120), nullable=True)
    units_count = Column(Integer, nullable=True, default=0)
    units_summary = Column(JSON, nullable=True)  # sample minted 3D-ULPINs

    twin = Column(JSON, nullable=True)  # full extruded twin record
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("ulpin", name="uq_national_twins_ulpin"),
    )

    def __repr__(self) -> str:
        return f"<NationalTwin {self.ulpin} {self.structure_code} fsi={self.fsi}>"