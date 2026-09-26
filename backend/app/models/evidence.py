from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, JSON, Boolean, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class EvidenceSource(Base):
    __tablename__ = "evidence_sources"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type = Column(String(50), nullable=False, index=True)  # GIS_PARCEL, DRONE_EPOCH1, DRONE_EPOCH2, LIDAR, FLOOR_PLAN, GNSS_CORS, DEM_DSM
    name = Column(String(200), nullable=False)
    confidence_tier = Column(String(20), nullable=False, default="TIER_B")  # TIER_A (Survey), TIER_B (Builder), TIER_C (Citizen)
    description = Column(String(255), nullable=True)

    assets = relationship("EvidenceAsset", back_populates="source")


class EvidenceAsset(Base):
    __tablename__ = "evidence_assets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(String(36), ForeignKey("evidence_sources.id"), nullable=False)
    submission_id = Column(String(36), ForeignKey("submissions.id"), nullable=True)
    
    file_name = Column(String(255), nullable=False)
    storage_key = Column(String(500), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)  # SHA-256
    file_size_bytes = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    crs = Column(String(50), default="EPSG:7755")  # India National Grid / EPSG:4326
    
    # Metadata & Quality
    quality_metric = Column(Float, nullable=True)  # e.g., Point density (pts/m2) or Resolution (cm/px)
    quality_notes = Column(String(255), nullable=True)
    provenance_details = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    source = relationship("EvidenceSource", back_populates="assets")
    submission = relationship("Submission", back_populates="evidence_assets")
    derived_geometries = relationship("DerivedGeometry", back_populates="asset")


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    receipt_number = Column(String(50), unique=True, nullable=False, index=True)
    submitter_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    parcel_id = Column(String(36), ForeignKey("parcels.id"), nullable=False)
    
    contributor_type = Column(String(50), nullable=False)  # BUILDER, CITIZEN, SURVEY_OFFICER, OFFICIAL
    status = Column(String(50), default="SUBMITTED")       # SUBMITTED, INGESTING, PROCESSING, VALIDATED, NEEDS_REVIEW, APPROVED, REJECTED
    declared_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    submitter = relationship("User", back_populates="submissions")
    parcel = relationship("Parcel", back_populates="submissions")
    evidence_assets = relationship("EvidenceAsset", back_populates="submission")
    processing_jobs = relationship("ProcessingJob", back_populates="submission")
    verification_cases = relationship("VerificationCase", back_populates="submission")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    submission_id = Column(String(36), ForeignKey("submissions.id"), nullable=True)
    job_type = Column(String(100), nullable=False)  # LIDAR_EXTRACTION, FLOOR_SEGMENTATION, VOLUME_DELINEATION, CHANGE_DETECTION
    status = Column(String(50), default="PENDING")   # PENDING, RUNNING, COMPLETED, FAILED
    current_step = Column(String(100), default="Initialized")
    progress_pct = Column(Integer, default=0)
    
    metrics = Column(JSON, nullable=True)  # { "iou": 0.94, "elapsed_s": 3.8 }
    logs = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    submission = relationship("Submission", back_populates="processing_jobs")


class DerivedGeometry(Base):
    __tablename__ = "derived_geometries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(String(36), ForeignKey("evidence_assets.id"), nullable=True)
    feature_type = Column(String(50), nullable=False)  # BUILDING_FOOTPRINT, FLOOR_SLAB, VERTICAL_SOLID
    method = Column(String(200), nullable=False)       # "LiDAR RANSAC & Alpha Shape", "Z-density Histogram Peak"
    metric_name = Column(String(50), nullable=True)    # "IoU", "Floor Count Accuracy"
    metric_value = Column(Float, nullable=True)
    geometry_data = Column(JSON, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    asset = relationship("EvidenceAsset", back_populates="derived_geometries")
