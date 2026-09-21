from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base


class QRToken(Base):
    __tablename__ = "qr_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token = Column(String(64), unique=True, nullable=False, index=True)  # Secure random / hashed token
    parcel_ulpin = Column(String(14), nullable=False, index=True)
    proposed_3d_id = Column(String(100), nullable=False)
    version_tag = Column(String(20), nullable=False, default="V1")
    
    # Cryptographic proof attachments
    fingerprint_sha256 = Column(String(64), nullable=False)
    signature_ed25519 = Column(String(128), nullable=False)
    signer_public_key = Column(String(64), nullable=False)
    
    # Non-sensitive public summary snapshot
    public_summary = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    verifications = relationship("PublicVerification", back_populates="qr_token", cascade="all, delete-orphan")


class PublicVerification(Base):
    __tablename__ = "public_verifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    qr_token_id = Column(String(36), ForeignKey("qr_tokens.id"), nullable=False)
    client_ip_hash = Column(String(64), nullable=True)  # SHA256 of IP for privacy
    verified_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    qr_token = relationship("QRToken", back_populates="verifications")
