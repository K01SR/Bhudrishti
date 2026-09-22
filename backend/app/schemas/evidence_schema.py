from typing import Optional, Dict, Any, List
from pydantic import BaseModel


class EvidenceAssetResponse(BaseModel):
    id: str
    source_type: str
    file_name: str
    file_hash: str
    file_size_bytes: int
    mime_type: str
    crs: str
    confidence_tier: str
    quality_metric: Optional[float] = None
    quality_notes: Optional[str] = None
    timestamp: str

    class Config:
        from_attributes = True


class SubmissionCreate(BaseModel):
    parcel_id: str
    contributor_type: str  # BUILDER, CITIZEN
    declared_data: Optional[Dict[str, Any]] = None


class SubmissionResponse(BaseModel):
    id: str
    receipt_number: str
    parcel_id: str
    contributor_type: str
    status: str
    created_at: str
    evidence_count: int = 0

    class Config:
        from_attributes = True


class ProcessingJobResponse(BaseModel):
    id: str
    job_type: str
    status: str
    current_step: str
    progress_pct: int
    metrics: Optional[Dict[str, Any]] = None
    created_at: str

    class Config:
        from_attributes = True
