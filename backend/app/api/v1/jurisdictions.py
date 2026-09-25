from typing import List, Dict, Any
from fastapi import APIRouter

router = APIRouter(prefix="/jurisdictions", tags=["Jurisdiction Administration"])

JURISDICTIONS = [
    {
        "id": "jur-airoli-sec08",
        "code": "MH-THN-AIR-SEC08",
        "name": "Airoli Sector 8",
        "state": "Maharashtra",
        "district": "Thane",
        "taluka": "Thane",
        "village_ward": "Ward 08 (Airoli)",
        "center": [19.1557, 72.9984],
        "max_fsi": 2.00,
        "metrics": {
            "total_parcels": 12,
            "mapped_3d_structures": 1,
            "verified_properties": 1,
            "pending_verification": 2,
            "open_conflicts": 1,  # Subsurface clash
            "suspected_unauthorized_changes": 1,
            "underground_clashes": 1,
            "data_completeness": "HIGH (6/6 Sources Ingested)",
        },
    },
    {
        "id": "jur-thane-wagle",
        "code": "MH-THN-WAG-IND",
        "name": "Wagle Estate Industrial Ward",
        "state": "Maharashtra",
        "district": "Thane",
        "taluka": "Thane",
        "village_ward": "Ward 14 (Wagle)",
        "center": [19.1912, 72.9514],
        "max_fsi": 2.50,
        "metrics": {
            "total_parcels": 24,
            "mapped_3d_structures": 4,
            "verified_properties": 3,
            "pending_verification": 1,
            "open_conflicts": 0,
            "suspected_unauthorized_changes": 0,
            "underground_clashes": 0,
            "data_completeness": "MEDIUM (4/6 Sources Ingested)",
        },
    },
]


@router.get("/")
def list_jurisdictions():
    """Lists administrative jurisdictions and high-level cadastral KPIs."""
    return JURISDICTIONS


@router.get("/state-summary")
def get_state_summary():
    """Returns high-level State Admin executive KPI metrics."""
    return {
        "state_name": "Maharashtra",
        "total_districts": 36,
        "active_pilot_districts": 1,  # Thane
        "total_mapped_parcels": 36,
        "total_3d_structures": 5,
        "total_strata_units": 108,
        "total_verified_properties": 4,
        "pending_verification_cases": 3,
        "total_open_conflicts": 1,
        "total_suspected_unauthorized_changes": 1,
        "total_underground_clashes": 1,
        "statewide_data_completeness": "87.4%",
    }
