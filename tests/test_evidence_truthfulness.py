"""
Guards on what the Evidence and Change Detection surfaces are allowed to claim.

The recurring failure here was not fabrication in the data layer. The backend
was honest and the frontend was not: it rendered fields the API never sends and
dropped the caveats the API does send. These tests pin the contract from both
ends so a UI that invents provenance fails here rather than in front of a user.
"""
import re

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture
def streams():
    response = client.get("/api/v1/evidence/")
    assert response.status_code == 200
    return response.json()


def test_evidence_streams_report_no_source_data(streams):
    """
    Every stream in the current deployment is a placeholder, so each must say
    so. If this ever starts failing because real data arrived, that is good
    news, and the provenance copy should be revisited at the same time.
    """
    assert streams
    for s in streams:
        assert s["available"] is False, f"{s['id']} claims to be available"
        assert s["confidence_tier"] == "None"
        assert "None" in s["provenance"] or "Not " in s["provenance"]


def test_evidence_streams_state_what_would_activate_them(streams):
    """A placeholder is only useful if it says what is missing."""
    for s in streams:
        assert s["required_to_activate"], f"{s['id']} does not say what would activate it"


def test_evidence_api_does_not_invent_fields(streams):
    """
    Pins the exact response shape.

    The UI previously typed and rendered stream_id, file_name, file_hash,
    timestamp, version, status and provenance_kind. The API sent none of them,
    so the card showed eight blank cells, and the SHA-256 heading sat above an
    empty value. Anything the UI wants to show has to exist here first.
    """
    expected = {
        "id",
        "name",
        "source_type",
        "available",
        "format",
        "crs",
        "confidence_tier",
        "provenance",
        "provenance_note",
        "quality_result",
        "required_to_activate",
    }
    assert expected.issubset(set(streams[0].keys()))
    for phantom in ("file_hash", "file_name", "timestamp", "provenance_kind"):
        assert phantom not in streams[0], (
            f"{phantom} is unexpectedly present; if it is now real, the frontend "
            "should be updated to display it rather than removed"
        )


def test_evidence_streams_are_counted_not_assumed():
    """
    The page claimed "Six ingested sources" as a literal while the API returned
    seven. The count must be derived, and this pins the real number so a change
    to the dataset is a deliberate update rather than a silent drift.
    """
    assert len(client.get("/api/v1/evidence/").json()) == 7


def test_change_detection_declares_its_inputs_synthetic():
    """
    The endpoint compares a hardcoded baseline against a demo dataset. There is
    no second survey on disk, so the response has to say so at the top level.
    """
    body = client.get("/api/v1/changes/compare").json()
    assert body["evidence_basis"] == "SYNTHETIC"
    assert body["detection_result"]["evidence_basis"] == "SYNTHETIC"
    assert body["evidence_disclosure"]["why_synthetic"]
    assert body["evidence_disclosure"]["not_a_finding"]
    assert len(body["evidence_disclosure"]["what_would_make_this_real"]) >= 2


def test_change_detection_does_not_allege_unauthorised_construction():
    """
    The response used to read "Suspected Unauthorized Change" and
    "Unsanctioned volumetric expansion", and the UI rendered "Unauthorized
    level" in red against a real parcel number. A difference between two
    supplied values is not evidence of an offence.
    """
    raw = client.get("/api/v1/changes/compare").text
    for phrase in ("Unauthorized Change", "Unsanctioned", "unauthorized"):
        assert phrase.lower() not in raw.lower(), f"{phrase!r} still alleges an offence"


def test_change_detection_wording_stays_neutral():
    result = client.get("/api/v1/changes/compare").json()["detection_result"]
    if result["change_detected"]:
        assert "difference" in " ".join(result["detected_features"]).lower()
        assert result["wording_note"]


def test_change_detection_arithmetic_is_still_correct():
    """
    The disclosure must not have been bought by neutering the computation. The
    pipeline still has to do the sums it claims to do.
    """
    from app.pipelines.change_detection import ChangeDetectionPipeline

    pipeline = ChangeDetectionPipeline()
    result = pipeline.detect_changes(
        epoch1_height=18.0,
        epoch2_height=21.5,
        epoch1_floors=5,
        epoch2_floors=6,
        footprint_area_m2=510.0,
    )
    assert result["change_detected"] is True
    assert result["delta_height_m"] == 3.5
    assert result["delta_floors"] == 1
    assert result["delta_volume_m3"] == 1785.0


def test_change_detection_no_change_path_is_still_reachable():
    """The threshold must still suppress sub-metre differences."""
    from app.pipelines.change_detection import ChangeDetectionPipeline

    result = ChangeDetectionPipeline().detect_changes(
        epoch1_height=18.0,
        epoch2_height=18.4,
        epoch1_floors=5,
        epoch2_floors=5,
        footprint_area_m2=510.0,
    )
    assert result["change_detected"] is False
    assert result["delta_height_m"] == 0.0
