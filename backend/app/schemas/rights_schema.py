from typing import Optional
from pydantic import BaseModel


class RightResponse(BaseModel):
    id: str
    unit_id: str
    unit_number: str
    proposed_3d_id: str
    party_name: str
    party_type: str
    right_type: str
    share_pct: float
    encumbrance_status: str
    financial_institution: Optional[str] = None
    mortgage_amount_inr: Optional[float] = None
    easement_purpose: Optional[str] = None
    is_synthetic: bool = True

    class Config:
        from_attributes = True
