"""What the point-cloud endpoints say when they refuse, and why.

The LiDAR routes used to refuse with one reason - the demo gate - which reads as
"an outage this deployment could fix by changing a setting". For these areas the
truth is that no open airborne LiDAR is published at all, and that is not
fixable by any configuration. These tests pin the distinction, and pin the
coverage table that the distinction rests on, so the finding cannot quietly rot
into a claim nobody checked.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.demo_gate import DemoDataDisabled, demo_mode_enabled, require_demo_mode
from app.core.lidar_coverage import (
    NO_COVERAGE_MESSAGE,
    OPEN_LIDAR_COVERAGE,
    open_lidar_coverage,
)

client = TestClient(__import__("app.main", fromlist=["app"]).app)


# --------------------------------------------------------------------------- #
# Coverage
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name,lat,lon",
    [
        ("Airoli Sector 8, the demo precinct", 19.0987, 72.9977),
        ("Bandra West", 19.0552, 72.8308),
        ("Delhi", 28.6139, 77.2090),
        ("Mumbai Fort", 18.9358, 72.8356),
        ("Bengaluru", 12.9716, 77.5946),
    ],
)
def test_no_precinct_this_product_serves_has_open_lidar(name, lat, lon):
    """Every area the product can be pointed at is outside open LiDAR coverage.

    This is the finding that closed the "stream real LiDAR" roadmap item, so it
    is asserted rather than only written down. If a future source starts
    publishing India, this fails and the refusal message needs revisiting.
    """
    assert open_lidar_coverage(lat, lon) is None, f"{name} unexpectedly has a verified open source"


def test_verified_sources_do_cover_the_places_they_claim():
    """A coverage table nobody spot-checks is a table of hopes."""
    assert open_lidar_coverage(50.85, 4.35) is not None, "Brussels, Belgium"
    assert open_lidar_coverage(55.68, 12.57) is not None, "Copenhagen, Denmark"
    assert open_lidar_coverage(38.90, -77.03) is not None, "Washington DC, US"
    # A country listed as covered must actually name its source.
    for code, src in OPEN_LIDAR_COVERAGE.items():
        assert src.get("bucket"), f"{code} has no bucket"
        assert src.get("format"), f"{code} has no format"


def test_the_refusal_does_not_claim_a_config_change_would_help():
    """The message must not imply the gate is the only obstacle."""
    assert "ENABLE_DEMO_MODE" not in NO_COVERAGE_MESSAGE
    assert "no environment variable changes it" in NO_COVERAGE_MESSAGE
    # It should point at what *is* available, so the refusal is a next step.
    assert "GlobalML" in NO_COVERAGE_MESSAGE
    assert "Terrain Tiles" in NO_COVERAGE_MESSAGE


# --------------------------------------------------------------------------- #
# The note travels with the refusal
# --------------------------------------------------------------------------- #
def test_a_data_note_is_carried_on_the_exception(monkeypatch: pytest.MonkeyPatch):
    # conftest opens the gate for the rest of the suite, so close it here or
    # there is nothing to refuse.
    monkeypatch.setenv("ENABLE_DEMO_MODE", "0")
    with pytest.raises(DemoDataDisabled) as exc:
        require_demo_mode("LiDAR point cloud", note=NO_COVERAGE_MESSAGE)
    assert exc.value.note == NO_COVERAGE_MESSAGE


def test_no_note_means_no_note(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "0")
    with pytest.raises(DemoDataDisabled) as exc:
        require_demo_mode("Something else")
    assert exc.value.note is None


def test_the_gate_still_opens(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    assert demo_mode_enabled() is True
    require_demo_mode("LiDAR point cloud", note=NO_COVERAGE_MESSAGE)  # must not raise


def test_refused_lidar_routes_explain_that_no_data_is_published(monkeypatch: pytest.MonkeyPatch):
    """The response separates "this deployment is shut" from "this data is absent"."""
    monkeypatch.setenv("ENABLE_DEMO_MODE", "0")
    for path in (
        "/api/v1/lidar/pointcloud",
        "/api/v1/lidar/inspect/scene",
        "/api/v1/lidar/inspect/points",
    ):
        res = client.get(path)
        assert res.status_code == 503, f"{path} -> {res.status_code}"
        body = res.json()
        assert body["demo_mode"] == "disabled"
        note = body.get("data_note")
        assert note, f"{path} refused without saying why the data itself is absent"
        assert "no open airborne lidar" in note.lower()
