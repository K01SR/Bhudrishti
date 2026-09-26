from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, JSON, Boolean, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class Right(Base):
    __tablename__ = "rights"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    unit_id = Column(String(36), ForeignKey("units.id"), nullable=False)
    party_id = Column(String(36), ForeignKey("parties.id"), nullable=False)
    
    right_type = Column(String(50), nullable=False)  # OWNERSHIP, MORTGAGE, LEASE, EASEMENT, RESTRICTION
    share_pct = Column(Float, default=100.0)
    encumbrance_status = Column(String(50), default="ACTIVE")  # ACTIVE, RELEASED, DISPUTED
    
    financial_institution = Column(String(200), nullable=True)  # caller-supplied label; no FI lookup is performed
    mortgage_amount_inr = Column(Float, nullable=True)
    easement_purpose = Column(String(255), nullable=True)       # e.g., "Shared Stairwell & Fire Egress Access"
    
    valid_from = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    valid_to = Column(DateTime(timezone=True), nullable=True)
    is_synthetic = Column(Boolean, default=True)  # Synthetic demo data label

    unit = relationship("Unit", back_populates="rights")
    party = relationship("Party", back_populates="rights")
