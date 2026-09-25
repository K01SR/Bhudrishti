from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.security import require_roles, TokenPayload, RoleEnum

router = APIRouter(prefix="/objections", tags=["Citizen Objections & Grievance Routing"])

CITIZEN_FILE = require_roles([RoleEnum.CITIZEN, RoleEnum.BUILDER, RoleEnum.STATE_ADMIN])
OFFICER_RESOLVE = require_roles([RoleEnum.TALUKA_VERIFIER, RoleEnum.DISTRICT_VERIFIER, RoleEnum.STATE_ADMIN])

_CATEGORY_DEPARTMENT = {
    "RESOLUTION": "Revenue & Land Records",
    "DATA": "Survey & Mapping",
    "AUTHORIZATION": "Urban Development",
    "OTHER": "Citizen Services",
}

_SEED = [
    {
        "case_number": "OBJ-2026-0001",
        "ulpin": "12345678901234",
        "category": "AUTHORIZATION",
        "description": "Neighbour objects to the reported 4th-floor addition on B-17; structure height appears to exceed the approved 18 m on the pending Epoch-2 survey.",
        "contact_email_redacted": "cit•••@example.com",
        "status": "OPEN",
        "department": "Urban Development",
        "assigned_role": "DISTRICT_VERIFIER",
        "priority": "HIGH",
        "created_at": "2026-09-18T09:40:00Z",
        "resolution": None,
        "resolved_at": None,
    },
    {
        "case_number": "OBJ-2026-0002",
        "ulpin": "12345678901240",
        "category": "DATA",
        "description": "Request to correct the recorded parcel boundary along the storm-water drain after re-survey.",
        "contact_email_redacted": "ve•••@example.com",
        "status": "RESOLVED",
        "department": "Survey & Mapping",
        "assigned_role": "TALUKA_VERIFIER",
        "priority": "MEDIUM",
        "created_at": "2026-08-30T12:10:00Z",
        "resolution": "Boundary corrected post re-survey; mutation recorded under CTS-106.",
        "resolved_at": "2026-09-05T11:00:00Z",
    },
]

_OBJECTIONS_DB: List[Dict[str, Any]] = []


def _seed_if_empty() -> None:
    if not _OBJECTIONS_DB:
        _OBJECTIONS_DB.extend(_SEED)


def list_open_objects_for_ulpin(ulpin: str) -> List[Dict[str, Any]]:
    """Module-level helper shared by integrity scoring (no FastAPI dependency)."""
    _seed_if_empty()
    return [o for o in _OBJECTIONS_DB if o["ulpin"] == ulpin and o["status"] == "OPEN"]


class ObjectionCreate(BaseModel):
    ulpin: str
    category: str = "OTHER"
    description: str
    contact_email: str = "user@example.com"
    priority: str = "MEDIUM"


class ObjectionResolve(BaseModel):
    resolution: str
    actor: str = "usr-district-admin"


@router.get("/")
def list_objections(ulpin: Optional[str] = None, status: Optional[str] = None):
    """List filings, optionally filtered by parcel ULPIN or status."""
    _seed_if_empty()
    rows = _OBJECTIONS_DB
    if ulpin:
        rows = [r for r in rows if r["ulpin"] == ulpin]
    if status:
        rows = [r for r in rows if r["status"] == status.upper()]
    return rows


@router.get("/departments")
def objection_departments():
    """Per-department worklist for the Citizen Services hub."""
    _seed_if_empty()
    counts: Dict[str, Dict[str, Any]] = {}
    for o in _OBJECTIONS_DB:
        d = o["department"]
        c = counts.setdefault(d, {"department": d, "total": 0, "open": 0, "resolved": 0, "latest": None})
        c["total"] += 1
        c["open"] += o["status"] == "OPEN"
        c["resolved"] += o["status"] == "RESOLVED"
        c["latest"] = max(c["latest"] or "", o["created_at"])
    return sorted(counts.values(), key=lambda c: -c["open"])


@router.post("/", status_code=201)
def create_objection(req: ObjectionCreate, _auth: TokenPayload = Depends(CITIZEN_FILE)):
    """File a new citizen objection; auto-routes to the responsible department."""
    _seed_if_empty()
    num = len(_OBJECTIONS_DB) + 1
    case_number = f"OBJ-2026-{num:04d}"
    dept = _CATEGORY_DEPARTMENT.get(req.category.upper(), "Citizen Services")
    email = req.contact_email.strip()
    redacted = (email[:3] + "•••" + email[email.find("@"):]) if "@" in email else email[:3] + "•••"
    record = {
        "case_number": case_number,
        "ulpin": req.ulpin.strip(),
        "category": req.category.upper(),
        "description": req.description.strip(),
        "contact_email_redacted": redacted,
        "status": "OPEN",
        "department": dept,
        "assigned_role": "TALUKA_VERIFIER",
        "priority": req.priority.upper(),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "resolution": None,
        "resolved_at": None,
    }
    _OBJECTIONS_DB.append(record)
    return record


@router.post("/{case_number}/resolve")
def resolve_objection(case_number: str, req: ObjectionResolve, _auth: TokenPayload = Depends(OFFICER_RESOLVE)):
    """Close an objection with a resolution note and actor stamp."""
    _seed_if_empty()
    record = next((o for o in _OBJECTIONS_DB if o["case_number"] == case_number), None)
    if not record:
        raise HTTPException(status_code=404, detail="Objection case not found")
    record["status"] = "RESOLVED"
    record["resolution"] = req.resolution.strip()
    record["resolved_by"] = req.actor
    record["resolved_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return record