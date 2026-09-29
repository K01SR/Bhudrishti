import uuid
import time
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.security import get_current_user_required, get_current_user_payload, require_roles, TokenPayload, RoleEnum
from app.pipelines.synthetic_generator import generate_synthetic_airoli_dataset
from app.pipelines.building_extraction import BuildingExtractionPipeline
from app.pipelines.floor_segmentation import FloorSegmentationPipeline
from app.qa_engine.rules import TopologyQAEngine

router = APIRouter(prefix="/submissions", tags=["Submissions & Ingestion Pipeline"])

# In-memory submissions store for hero flow
_SUBMISSIONS_DB = [
    {
        "id": "sub-b17-001",
        "receipt_number": "SUB-MH-2026-B17-0891",
        "submitter_name": "Apex InfraProjects Ltd (Builder)",
        "parcel_id": "12345678901234",
        "building_code": "B-17",
        "contributor_type": "BUILDER",
        "status": "APPROVED",
        "created_at": "2026-09-24T09:30:00Z",
        "evidence_files": [
            "airoli_b17_classified.laz",
            "drone_orthomosaic_epoch1.tif",
            "b17_sanction_plans_approved.dwg",
            "cors_differential_corrections.csv",
        ],
    },
    {
        "id": "sub-b17-002",
        "receipt_number": "SUB-MH-2026-B17-0942",
        "submitter_name": "Karan Malhotra (Citizen / Buyer)",
        "parcel_id": "12345678901234",
        "building_code": "B-17",
        "contributor_type": "CITIZEN",
        "status": "NEEDS_REVIEW",
        "created_at": "2026-09-24T14:15:00Z",
        "evidence_files": [
            "flat_201_possession_receipt.pdf",
            "flat_201_interior_survey.jpg",
        ],
    },
]


class SubmissionCreateReq(BaseModel):
    parcel_id: str
    building_code: str
    contributor_type: str = "BUILDER"
    notes: Optional[str] = None


@router.get("/")
def list_submissions():
    """Lists all spatial evidence submissions."""
    return _SUBMISSIONS_DB


@router.post("/create")
def create_submission(
    req: SubmissionCreateReq,
    _auth: TokenPayload = Depends(require_roles([RoleEnum.BUILDER, RoleEnum.STATE_ADMIN])),
):
    """Creates a new submission record with generated tracking receipt."""
    receipt = f"SUB-MH-2026-{uuid.uuid4().hex[:6].upper()}"
    new_sub = {
        "id": f"sub-{uuid.uuid4().hex[:8]}",
        "receipt_number": receipt,
        "submitter_name": _auth.sub,
        "parcel_id": req.parcel_id,
        "building_code": req.building_code,
        "contributor_type": req.contributor_type,
        "status": "SUBMITTED",
        "created_at": "2026-09-24T18:00:00Z",
        "evidence_files": ["sanction_plan.dwg", "site_survey.csv"],
    }
    _SUBMISSIONS_DB.append(new_sub)
    return new_sub


@router.post("/process-property")
def process_hero_property(
    _auth: TokenPayload = Depends(require_roles([RoleEnum.BUILDER, RoleEnum.DISTRICT_VERIFIER, RoleEnum.STATE_ADMIN])),
):
    """Runs the spatial pipeline over the generated Airoli dataset and reports it.

    Demo-only: the input is ``generate_synthetic_airoli_dataset()``, not a survey.

    The previous version returned a six-stage trace in which every stage was
    ``COMPLETED`` at 100% with a hardcoded ``latency_ms`` (120/45/280/190/310/220),
    a stage labelled "PostGIS/SFCGAL 12-Rule QA Check" reporting "1 Subsurface
    Clash Detected" and a clash described as "PIPE-DRAIN-01 intersects Basement at
    Z=-3.2m", plus an ``extraction_summary.measured_iou`` of 0.94. None of it was
    measured: only three pipeline calls actually execute here, "21 Bounded Solids"
    came from no extrusion step at all, and there is no SFCGAL in this repository.

    So the trace below is built from ``time.perf_counter()`` around the calls that
    really run, and only those calls. Stages that previously appeared without a
    corresponding execution are absent rather than reported as passed.
    """
    from app.core.demo_gate import require_demo_mode
    require_demo_mode("Spatial Ingestion Pipeline (synthetic input)")

    stages: List[Dict[str, Any]] = []

    # Stage 1: dataset generation is a real call, so it is really timed.
    t0 = time.perf_counter()
    dataset = generate_synthetic_airoli_dataset()
    stages.append({
        "stage": "1. Synthetic Dataset Generation",
        "status": "COMPLETED",
        "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        "metric": f"{len(dataset.get('synthetic_lidar_points', []))} points",
        "source": "generated (not a survey)",
    })

    pts = dataset["synthetic_lidar_points"]
    extractor = BuildingExtractionPipeline()
    segmenter = FloorSegmentationPipeline()
    qa_engine = TopologyQAEngine()

    # Stage 2: building extraction from the point cloud
    t0 = time.perf_counter()
    extract_res = extractor.extract_from_points(pts)
    stages.append({
        "stage": "2. LiDAR Building Extraction",
        "status": "COMPLETED",
        "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        "metric": f"height {extract_res.get('extracted_height_m')} m",
    })

    # Stage 3: floor segmentation
    t0 = time.perf_counter()
    seg_res = segmenter.segment_floors(pts, ground_z=0.0, has_basement=True)
    stages.append({
        "stage": "3. Z-Density Slab Segmentation",
        "status": "COMPLETED",
        "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        "metric": f"{seg_res.get('detected_floor_count')} floors"
                  f"{' + basement' if seg_res.get('has_basement') else ''}",
    })

    # Stage 4: topology QA. Rule outcomes come from the engine, not a literal.
    t0 = time.perf_counter()
    qa_res = qa_engine.run_all_rules(
        parcel_data=dataset["hero_parcel"],
        structure_data=dataset["hero_structure"],
        levels_data=dataset["levels"],
        units_data=dataset["units"],
        subsurface_objects=dataset["subsurface_objects"],
    )
    findings = qa_res.get("findings", [])
    failing = [f for f in findings if str(getattr(f.get("status"), "value", f.get("status"))).upper() != "PASS"]
    stages.append({
        "stage": "4. Topology QA Rules",
        "status": qa_res.get("overall_status", "UNKNOWN"),
        "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        "metric": f"{qa_res.get('passed_rules')} passed, "
                  f"{qa_res.get('failed_rules')} failed, "
                  f"{qa_res.get('warning_rules')} warned "
                  f"({qa_res.get('total_rules')} rules)",
    })

    return {
        "pipeline_status": "COMPLETED",
        "provenance": {
            "source": "generated (not a survey)",
            "is_synthetic": True,
            "authoritative": False,
        },
        "execution_stages": stages,
        "extraction_summary": {
            "building_code": "B-17",
            "building_code_source": "demo scenario label, not a surveyed identifier",
            "extracted_height_m": extract_res["extracted_height_m"],
            "detected_floors": seg_res["detected_floor_count"],
            "has_basement": seg_res["has_basement"],
            "total_strata_units": len(dataset["units"]),
            "total_strata_units_source": "generated; not a floor-unit registry",
            # No ground-truth polygon exists for a generated point cloud, so an
            # intersection-over-union figure would be an invented accuracy score.
            "measured_iou": None,
        },
        "topology_summary": {
            "passed_rules": qa_res["passed_rules"],
            "failed_rules": qa_res["failed_rules"],
            "warning_rules": qa_res["warning_rules"],
            "overall_status": qa_res.get("overall_status"),
            # Rule messages verbatim from the engine, instead of a hardcoded
            # clash id and depth that no computation produced.
            "findings": [
                {
                    "rule_id": f.get("rule_id"),
                    "status": str(getattr(f.get("status"), "value", f.get("status"))),
                    "message": f.get("message"),
                }
                for f in findings
            ],
        },
    }
