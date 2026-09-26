from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Integer, DateTime, JSON, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class DatasetAsset(Base):
    """A real ingested point-cloud / imagery asset, hash-bound to its bytes."""

    __tablename__ = "dataset_assets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dataset_id = Column(String(100), nullable=False, index=True)
    dataset_name = Column(String(200), nullable=False)
    storage_path = Column(String(400), nullable=False)
    format = Column(String(10), nullable=False)  # las, laz, csv, tif, geojson
    bytes = Column(Integer, nullable=False, default=0)
    file_sha256 = Column(String(64), nullable=False, index=True)
    crs_epsg = Column(Integer, nullable=True, default=32643)
    provenance = Column(JSON, nullable=True)
    registered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    runs = relationship("PipelineRun", back_populates="asset")


class PipelineRun(Base):
    """Audit-bound VC-X run over a real asset, with verified native metrics."""

    __tablename__ = "pipeline_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_id = Column(String(100), nullable=False, default="vertical-cadastre-extraction")
    run_hash = Column(String(64), unique=True, nullable=False, index=True)
    asset_id = Column(String(36), ForeignKey("dataset_assets.id"), nullable=True)
    actor_id = Column(String(100), nullable=True, default="system-pipeline")
    status = Column(String(30), nullable=False, default="SUCCESS")
    metrics = Column(JSON, nullable=True)
    engine = Column(JSON, nullable=True)
    stages = Column(JSON, nullable=True)
    provenance = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    asset = relationship("DatasetAsset", back_populates="runs")