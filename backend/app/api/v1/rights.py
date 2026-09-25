from typing import List, Dict, Any
from fastapi import APIRouter, Depends
from app.core.demo_gate import demo_mode_dependency, load_demo_dataset

router = APIRouter(prefix="/rights", tags=["Rights & Encumbrances Layer"])

_DATASET = load_demo_dataset()


@router.get("/summary")
def get_rights_summary(_guard: None = Depends(demo_mode_dependency)):
    """Returns rights breakdown for all units in Building B-17."""
    return {
        "disclaimer": "SYNTHETIC DEMO DATA — Legal rights and mortgage representations are technical simulations.",
        "rights_types": ["OWNERSHIP", "MORTGAGE", "LEASE", "EASEMENT", "RESTRICTION"],
        "hero_case_unit_201": {
            "unit_number": "201",
            "proposed_3d_id": "12345678901234/UB17-L02-201-X",
            "active_encumbrances": [
                {
                    "type": "OWNERSHIP",
                    "party": "Karan Malhotra & Priya Malhotra",
                    "share": "100%",
                    "color": "#10B981",
                },
                {
                    "type": "MORTGAGE",
                    "party": "State Bank of India (Airoli Branch)",
                    "amount_inr": "₹ 85,00,000",
                    "status": "ACTIVE_LIEN",
                    "color": "#EF4444",
                },
                {
                    "type": "EASEMENT",
                    "party": "Building B-17 CHS Common Area",
                    "purpose": "Corridor & Fire Egress Access Easement",
                    "color": "#3B82F6",
                },
            ],
        },
    }


@router.get("/color-modes")
def get_color_modes():
    """Returns colour keys for the 3D viewer.

    These are demo rendering categories. No colour here represents an official
    approval, a title status, a survey grade, or any finding by an authority.
    """
    return {
        "modes": [
            {
                "id": "verification",
                "label": "Verification Status",
                "legend": [
                    {"label": "Marked Verified In Demo", "color": "#10B981"},
                    {"label": "Awaiting A Decision In Demo", "color": "#F59E0B"},
                    {"label": "Flagged Discrepancy In Demo", "color": "#EF4444"},
                ],
            },
            {
                "id": "rights",
                "label": "Rights & Encumbrance",
                "legend": [
                    {"label": "Ownership Right Only (Demo)", "color": "#10B981"},
                    {"label": "Simulated Mortgage Right", "color": "#EF4444"},
                    {"label": "Easement / Common Egress", "color": "#3B82F6"},
                    {"label": "Subterranean Common Parking", "color": "#6B7280"},
                ],
            },
            {
                "id": "confidence",
                "label": "Evidence Confidence Tier",
                "legend": [
                    {"label": "Tier A (Demo High Confidence)", "color": "#10B981"},
                    {"label": "Tier B (Demo Medium Confidence)", "color": "#3B82F6"},
                    {"label": "Tier C (Demo Low Confidence)", "color": "#F59E0B"},
                ],
            },
            {
                "id": "conflict",
                "label": "Topology & Subsurface Conflicts",
                "legend": [
                    {"label": "No Clash Computed", "color": "#10B981"},
                    {"label": "Flagged Subsurface Clash (Demo)", "color": "#DC2626"},
                    {"label": "Boundary Warning", "color": "#F59E0B"},
                ],
            },
            {
                "id": "type",
                "label": "Spatial Entity Type",
                "legend": [
                    {"label": "Residential Unit (U)", "color": "#3B82F6"},
                    {"label": "Parking Bay (P)", "color": "#6B7280"},
                    {"label": "Underground Pipe/Tunnel (X)", "color": "#8B5CF6"},
                    {"label": "Elevated Skywalk (E)", "color": "#EC4899"},
                    {"label": "Air-Right Envelope (A)", "color": "#06B6D4"},
                ],
            },
        ]
    }
