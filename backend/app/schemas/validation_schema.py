from typing import Optional, Dict, Any, List
from pydantic import BaseModel


class TopologyIssueResponse(BaseModel):
    id: str
    rule_id: str
    rule_name: str
    severity: str
    status: str
    entity_type: str
    entity_id: Optional[str] = None
    message: str
    conflict_geometry: Optional[Dict[str, Any]] = None
    recommended_action: Optional[str] = None

    class Config:
        from_attributes = True


class ValidationRunResponse(BaseModel):
    id: str
    parcel_id: str
    status: str
    total_rules: int
    passed_rules: int
    failed_rules: int
    warning_rules: int
    summary: Optional[Dict[str, Any]] = None
    issues: List[TopologyIssueResponse] = []

    class Config:
        from_attributes = True


class VerificationDecision(BaseModel):
    decision: str  # APPROVE, REJECT, CORRECTION_REQUESTED
    officer_notes: str
    correction_details: Optional[str] = None


class VerificationCaseResponse(BaseModel):
    id: str
    case_number: str
    parcel_id: str
    parcel_ulpin: str
    submission_id: Optional[str] = None
    assigned_verifier_id: Optional[str] = None
    status: str
    case_type: str
    priority: str
    officer_notes: Optional[str] = None
    correction_details: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True
