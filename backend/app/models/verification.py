from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, JSON, Boolean, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class VerificationCase(Base):
    __tablename__ = "verification_cases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_number = Column(String(50), unique=True, nullable=False, index=True)
    parcel_id = Column(String(36), ForeignKey("parcels.id"), nullable=False)
    submission_id = Column(String(36), ForeignKey("submissions.id"), nullable=True)
    assigned_verifier_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    
    status = Column(String(50), default="NEEDS_REVIEW")  # NEEDS_REVIEW, APPROVED, REJECTED, CORRECTION_REQUESTED
    case_type = Column(String(50), default="NEW_PROPERTY_REGISTRATION") # NEW_PROPERTY_REGISTRATION, DISCREPANCY_REVIEW, UNAUTHORIZED_CHANGE
    priority = Column(String(20), default="HIGH")        # CRITICAL, HIGH, MEDIUM, LOW
    
    officer_notes = Column(Text, nullable=True)
    correction_details = Column(Text, nullable=True)
    # What "accepted" means here. Carries RECORD_BASIS so a database acceptance
    # never reads like a registry certificate (see builder_submissions module).
    basis = Column(String(500), nullable=True)
    decision_timestamp = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    parcel = relationship("Parcel", back_populates="verification_cases")
    submission = relationship("Submission", back_populates="verification_cases")
    assigned_verifier = relationship("User", foreign_keys=[assigned_verifier_id])


class PropertyChange(Base):
    __tablename__ = "property_changes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    structure_id = Column(String(36), ForeignKey("structures.id"), nullable=False)
    change_type = Column(String(50), nullable=False)  # NEW_FLOOR, HEIGHT_INCREASE, FOOTPRINT_CHANGE
    epoch_from = Column(String(50), nullable=False)   # "2026 Epoch 1"
    epoch_to = Column(String(50), nullable=False)     # "2027 Epoch 2"
    
    status = Column(String(100), default="Suspected change (unverified)")  # Domain-safe wording; see change_detection
    delta_height_m = Column(Float, nullable=True)
    delta_volume_m3 = Column(Float, nullable=True)
    delta_floors = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    change_geometry = Column(JSON, nullable=True)     # Geometry of added floor / changed volume
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PropertyVersion(Base):
    __tablename__ = "property_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parcel_ulpin = Column(String(14), nullable=False, index=True)
    version_tag = Column(String(20), nullable=False)  # "V1", "V2", "V3"
    
    canonical_snapshot = Column(JSON, nullable=False)
    fingerprint_sha256 = Column(String(64), nullable=False)
    signature_ed25519 = Column(String(128), nullable=False)
    signer_public_key = Column(String(64), nullable=False)
    
    verified_by_officer = Column(String(100), nullable=False)
    verification_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
