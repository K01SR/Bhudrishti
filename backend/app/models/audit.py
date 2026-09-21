from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Text
from app.core.database import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_number = Column(Integer, autoincrement=True, unique=True, index=True)
    event_type = Column(String(100), nullable=False)   # SUBMISSION_CREATED, EVIDENCE_UPLOADED, PROCESSING_STARTED, etc.
    entity_type = Column(String(50), nullable=False)   # PARCEL, STRUCTURE, UNIT, CASE, SUBMISSION
    entity_id = Column(String(100), nullable=False)
    actor_id = Column(String(100), nullable=False)    # User ID or "SYSTEM"
    
    # Tamper-evident SHA-256 Hash Chain
    previous_hash = Column(String(64), nullable=False)
    current_hash = Column(String(64), nullable=False, unique=True)
    
    payload = Column(JSON, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    raw_query = Column(Text, nullable=False)
    parsed_intent = Column(String(100), nullable=False)
    matched_category = Column(String(100), nullable=False)
    filter_params = Column(JSON, nullable=True)
    results_count = Column(Integer, default=0)
    execution_time_ms = Column(Float, nullable=False)
    actor_id = Column(String(100), default="ANONYMOUS")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ExportRecord(Base):
    __tablename__ = "exports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    export_format = Column(String(20), nullable=False)  # CITYJSON, GEOJSON, CANONICAL_JSON, CSV
    target_entity = Column(String(100), nullable=False) # e.g. "Parcel 12345678901234 / B-17"
    file_size_bytes = Column(Integer, nullable=False)
    download_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuditCheckpoint(Base):
    """Externally signed anchor over the audit chain head.

    Separate from ``audit_events`` on purpose. The chain proves ordering; this
    proves the chain was not rewritten by someone holding only database
    credentials. An attacker who rewrites the events cannot forge this
    signature without the Ed25519 private key, which is kept outside the
    database.
    """
    __tablename__ = "audit_checkpoints"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    checkpoint_number = Column(Integer, unique=True, nullable=False, index=True)
    head_hash = Column(String(64), nullable=False)
    head_event_number = Column(Integer, nullable=False)
    event_count = Column(Integer, nullable=False)

    # Null only when no Ed25519 keypair is configured; an unsigned checkpoint is
    # stored and reported as unsigned rather than silently trusted.
    signature = Column(String(256), nullable=True)
    public_key_hex = Column(String(64), nullable=True)
    algorithm = Column(String(20), nullable=True)

    note = Column(Text, nullable=True)
    # Set when a later checkpoint supersedes this one, e.g. an unsigned seal
    # replaced once a keypair was configured, or a checkpoint written by a
    # build with a signature bug. Superseded rows are kept, never deleted, so
    # the history of what was believed and when stays auditable.
    superseded_by = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
