from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(50), unique=True, nullable=False, index=True)  # STATE_ADMIN, DISTRICT_VERIFIER, etc.
    description = Column(String(255), nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=False)
    role_name = Column(String(50), nullable=False, default="PUBLIC")
    is_active = Column(Boolean, default=True)
    jurisdiction_id = Column(String(36), ForeignKey("jurisdictions.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    jurisdiction = relationship("Jurisdiction", back_populates="users")
    submissions = relationship("Submission", back_populates="submitter")


class Party(Base):
    __tablename__ = "parties"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    party_type = Column(String(50), nullable=False)  # NATURAL_PERSON, FINANCIAL_INSTITUTION, GOVT_AGENCY, BUILDER
    name = Column(String(255), nullable=False)
    synthetic_id = Column(String(50), nullable=True)  # e.g., "SYN-PAN-9021"
    contact_email = Column(String(255), nullable=True)
    is_synthetic = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    rights = relationship("Right", back_populates="party")
