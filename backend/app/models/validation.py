from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, JSON, Boolean, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parcel_id = Column(String(36), ForeignKey("parcels.id"), nullable=False)
    structure_id = Column(String(36), ForeignKey("structures.id"), nullable=True)
    status = Column(String(50), default="COMPLETED")  # RUNNING, COMPLETED, FAILED
    
    total_rules = Column(Integer, default=12)
    passed_rules = Column(Integer, default=0)
    failed_rules = Column(Integer, default=0)
    warning_rules = Column(Integer, default=0)
    summary = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    issues = relationship("TopologyIssue", back_populates="validation_run", cascade="all, delete-orphan")


class TopologyIssue(Base):
    __tablename__ = "topology_issues"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    validation_run_id = Column(String(36), ForeignKey("validation_runs.id"), nullable=False)
    rule_id = Column(String(20), nullable=False, index=True)  # R001 to R016
    rule_name = Column(String(200), nullable=False)
    severity = Column(String(20), nullable=False)             # CRITICAL, HIGH, MEDIUM, LOW
    status = Column(String(50), default="OPEN")               # OPEN, RESOLVED, WAIVED
    
    entity_type = Column(String(50), nullable=False)          # STRUCTURE, UNIT, SUBSURFACE, PARCEL
    entity_id = Column(String(100), nullable=True)
    message = Column(Text, nullable=False)
    conflict_geometry = Column(JSON, nullable=True)
    recommended_action = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    validation_run = relationship("ValidationRun", back_populates="issues")


class MetricRun(Base):
    __tablename__ = "metric_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    benchmark_name = Column(String(100), nullable=False)
    evaluated_entity = Column(String(100), nullable=False)  # e.g., "Building B-17 Ground Truth vs LiDAR Extracted"
    
    building_iou = Column(Float, nullable=True)
    building_precision = Column(Float, nullable=True)
    building_recall = Column(Float, nullable=True)
    floor_count_accuracy = Column(Float, nullable=True)
    floor_mae = Column(Float, nullable=True)
    change_detection_precision = Column(Float, nullable=True)
    change_detection_recall = Column(Float, nullable=True)
    change_detection_f1 = Column(Float, nullable=True)
    
    execution_time_seconds = Column(Float, nullable=False)
    measured_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
