"""
Multi-epoch change detection.

The important thing about this module is what the numbers are NOT.

The baseline below (18.0 m, 5 floors, 510 m²) is hardcoded, and the monitoring
epoch is read from the demo dataset. There is no second survey on disk, no
survey imagery, and no instrument report. What this endpoint therefore returns
is a worked example of the pipeline's output shape, not a finding about a
building.

It is reported as SYNTHETIC for that reason. A real deployment must supply both
epochs from an actual survey, and the deltas become meaningful only then; until
then a red "Unauthorized level" on screen would be a fabricated accusation
against a real named building.

The arithmetic itself is exercised for real, so the pipeline logic is testable
and correct. Only the inputs are synthetic.
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends
from app.core.demo_gate import demo_mode_dependency, load_demo_dataset
from app.pipelines.change_detection import ChangeDetectionPipeline

router = APIRouter(prefix="/changes", tags=["Multi-Epoch Change Detection"])

_DATASET = load_demo_dataset()
_CHANGE_PIPELINE = ChangeDetectionPipeline()

# Hardcoded baseline, kept as a named constant so its invented status is visible
# at the call site rather than buried in an argument list.
_SYNTHETIC_EPOCH1_HEIGHT_M = 18.0
_SYNTHETIC_EPOCH1_FLOORS = 5
_SYNTHETIC_FOOTPRINT_M2 = 510.0


@router.get("/compare")
def compare_epochs(_guard: None = Depends(demo_mode_dependency)):
    """
    Runs the change-detection pipeline over the synthetic epoch pair.

    Returns the deltas the pipeline computes, explicitly marked SYNTHETIC so
    that no caller can mistake them for a survey measurement.
    """
    epoch2_data = _DATASET["epoch2_change"]

    detection = _CHANGE_PIPELINE.detect_changes(
        epoch1_height=_SYNTHETIC_EPOCH1_HEIGHT_M,
        epoch2_height=epoch2_data.get("new_height_m", _SYNTHETIC_EPOCH1_HEIGHT_M),
        epoch1_floors=_SYNTHETIC_EPOCH1_FLOORS,
        epoch2_floors=epoch2_data.get("new_floor_count", _SYNTHETIC_EPOCH1_FLOORS),
        footprint_area_m2=_SYNTHETIC_FOOTPRINT_M2,
    )

    return {
        "building_code": "B-17",
        "parcel_ulpin": "12345678901234",
        # The single most important field in this response.
        "evidence_basis": "SYNTHETIC",
        "evidence_disclosure": {
            "why_synthetic": (
                "Both epochs are generated. The baseline height, floor count and "
                "footprint are hardcoded constants and the monitoring epoch comes "
                "from the demo dataset. No second survey, instrument report or "
                "imagery exists for this building."
            ),
            "not_a_finding": (
                "The height delta, added floors and volume below are arithmetic "
                "over invented inputs. They do not evidence unauthorised "
                "construction and must not be cited as if they did."
            ),
            "what_would_make_this_real": [
                "A dated baseline survey of the structure, with its own provenance.",
                "A later monitoring observation from a named instrument or campaign.",
                "Both epochs georeferenced to the same parcel, so the comparison is meaningful.",
            ],
        },
        "detection_result": detection,
        "epoch1": {
            "epoch_name": "2026 Epoch 1 Baseline Survey",
            "height_m": _SYNTHETIC_EPOCH1_HEIGHT_M,
            "floors_count": _SYNTHETIC_EPOCH1_FLOORS,
            "units_count": 21,
            # Was "APPROVED", which implies a sanction exists and was checked.
            # No sanction record was consulted, so the epoch is simply the
            # reference side of the comparison.
            "status": "Reference values",
            "sanction_verified": False,
            "source": "hardcoded constant, not a survey",
        },
        "epoch2": {
            "epoch_name": "2027 Epoch 2 Monitoring Survey",
            "height_m": epoch2_data.get("new_height_m", _SYNTHETIC_EPOCH1_HEIGHT_M),
            "floors_count": epoch2_data.get("new_floor_count", _SYNTHETIC_EPOCH1_FLOORS),
            "units_count": 21 + len(epoch2_data.get("added_units", [])),
            # Was SUSPECTED_UNAUTHORIZED_CHANGE. The word asserts an offence that
            # nothing here establishes: there is no survey, no sanction record
            # and no officer review, so the difference cannot be characterised
            # as unauthorised at all.
            "status": "Difference pending review",
            "authorisation_known": False,
            "added_units": epoch2_data.get("added_units", []),
            "source": "demo dataset, not a survey",
        },
    }
