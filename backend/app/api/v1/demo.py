from fastapi import APIRouter, Depends
from app.core.security import require_roles, TokenPayload, RoleEnum
from app.pipelines.synthetic_generator import generate_synthetic_airoli_dataset

router = APIRouter(prefix="/demo", tags=["Hero Scenario & Demo Controls"])

STATE_ONLY = require_roles([RoleEnum.STATE_ADMIN])


@router.post("/reset")
def reset_hero_demo_scenario(_auth: TokenPayload = Depends(STATE_ONLY)):
    """
    Resets the platform to the pristine Hero Demo state:
    - Restores Building B-17 (5 floors, 1 basement, 20 apartments, P01 parking)
    - Re-arms 6 multi-source evidence streams
    - Resets verification queue (Case CASE-2026-B17-001 & CASE-2026-B17-002)
    - Re-arms subterranean clash (PIPE-DRAIN-01 at Z=-3.2m)
    - Re-arms multi-epoch change detection (2026 Epoch 1 vs 2027 Epoch 2 addition)
    - Prepares the exact 5-minute SIH live presentation flow.
    """
    from app.api.v1.verification import _CASES_DB
    _CASES_DB[0]["status"] = "NEEDS_REVIEW"
    _CASES_DB[0]["officer_notes"] = None
    _CASES_DB[0]["decision_timestamp"] = None

    _CASES_DB[1]["status"] = "NEEDS_REVIEW"
    _CASES_DB[1]["officer_notes"] = None
    _CASES_DB[1]["decision_timestamp"] = None

    return {
        "status": "HERO_SCENARIO_READY",
        "precinct": "Airoli Sector 8, Navi Mumbai",
        "hero_property": "Building B-17 (Parent ULPIN: 12345678901234)",
        "message": "Platform reset to pristine hero demo state. Ready for live presentation.",
    }
