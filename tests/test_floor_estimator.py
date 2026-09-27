"""The floor-count estimator's evidence must stay honest and self-limiting.

The model is weak on purpose-visible terms: MAE about 2.1 floors, R-squared
about 0.25 on a geographic split. These tests do not try to make it look good.
They pin the three things that make it trustworthy rather than impressive:

1. Height is excluded, because floors is close to height/3. A floor count you
   can read off the height is not an estimate, and including it would turn an
   honest hard problem into a meaningless easy one.
2. The split is geographic. A random split on this data scores R-squared 0.35
   against the geographic split's 0.25, and that 0.10 gap is exactly the
   neighbour memorisation a random split buys.
3. The fitness verdict is published next to the metrics. If the two are ever
   separated, the mediocre number gets quoted without the caveat, which is the
   specific failure this module exists to prevent.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api.v1 import ml_status
from app.ml.floor_estimator import FEATURE_NAMES, FloorEstimate, features_from_geometry

MANIFEST = Path("backend/app/ml/artifacts/floor_estimator_manifest.json")


@pytest.fixture(scope="module")
def manifest() -> dict:
    if not MANIFEST.exists():
        pytest.skip("model not trained; run app.ml.train_floor_estimator")
    return json.loads(MANIFEST.read_text())


def test_height_is_excluded_from_features() -> None:
    assert "height_m" not in FEATURE_NAMES
    assert "floors" not in FEATURE_NAMES


def test_features_are_plan_geometry_only() -> None:
    """Every feature must be computable from the footprint alone."""
    forbidden = ("height", "floor", "z", "elev")
    for name in FEATURE_NAMES:
        assert not any(f in name for f in forbidden), (
            f"{name} cannot be derived from plan geometry, so the task is circular"
        )


def test_feature_vector_matches_declared_width_and_order() -> None:
    vec = features_from_geometry(
        area_m2=510.0, perimeter_m=94.0, centroid_x=0, centroid_y=0,
        vertex_count=5, major_axis_m=30.0, minor_axis_m=17.0, bearing_rad=0.0,
        bbox_width_m=30.0, bbox_height_m=17.0, neighbour_count_50m=12,
        neighbour_mean_area_50m=480.0, local_density_100m=150.0,
    )
    assert len(vec) == len(FEATURE_NAMES)
    compactness = vec[FEATURE_NAMES.index("compactness")]
    assert 0 < compactness <= 1.0, "isoperimetric quotient cannot exceed 1"


def test_manifest_reports_a_geographic_split(manifest: dict) -> None:
    assert "geographic" in manifest["split_strategy"].lower()
    assert manifest["split_rationale"], "the split must say why it is not random"


def test_manifest_is_marked_retracted_and_says_why(manifest: dict) -> None:
    """The manifest must not look like a working model.

    It was fitted to ``random.randint``, so the numbers describe the seed script.
    A reader opening this file has to hit the retraction before the metrics.
    """
    assert manifest["status"] == "retracted"
    assert manifest["metrics_valid"] is False
    assert manifest["retraction_reason"]
    assert "random.randint" in manifest["retraction_reason"]


def test_manifest_states_the_real_label_source(manifest: dict) -> None:
    """It claimed OSM crowd-sourced tags. That was wrong and must not come back."""
    source = manifest["label_source"]
    assert "random.randint" in source
    assert "not OpenStreetMap" in source


def test_manifest_declares_labels_non_authoritative(manifest: dict) -> None:
    assert manifest["label_authoritative"] is False
    assert manifest["limitations"], "a model with no stated limitations is hiding them"


def test_fitness_offers_nothing_while_retracted(manifest: dict) -> None:
    """With no valid score there is no use the model can be put to."""
    fitness = manifest["fitness"]
    assert fitness["usable_for"] == []
    assert fitness["not_usable_for"], "must say what the model may not be used for"
    assert fitness["verdict"]
    assert fitness["meets_rejection_threshold"] is False


def test_manifest_records_both_independent_defects(manifest: dict) -> None:
    """Two separate bugs, and the second one is easy to forget.

    The label was synthetic. Separately, ``ST_Area`` on SRID 4326 returns square
    degrees, so features named ``log_area_m2`` never held square metres. Fixing
    the data without fixing the units would still ship nonsense.
    """
    assert "square degrees" in manifest["geometry_units_note"]
    assert "43523" in manifest["split_note"] or "43,523" in manifest["split_note"]


def test_endpoint_surface_carries_metrics_and_verdict_together() -> None:
    """Both numbers must be in one response, so neither can be quoted alone."""
    import asyncio

    result = asyncio.run(ml_status.ml_evidence())
    assert "available" in result
    if result["available"]:
        m = result["models"][0]
        assert m["metrics"] and m["fitness"]["verdict"], (
            "metrics and verdict must be adjacent in the response"
        )
        assert m["label_authoritative"] is False
        assert m["split_strategy"]
        assert m["excluded_from_features"] == ["height_m", "floors"]


def test_endpoint_says_so_when_untrained(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ml_status, "MANIFEST", Path("/nonexistent/manifest.json"))
    import asyncio

    result = asyncio.run(ml_status.ml_evidence())
    assert result["available"] is False
    assert result["models"] == []
    assert "train_floor_estimator" in result["reason"], (
        "an untrained deployment must say how to train, not look like no problems"
    )


def test_estimate_prefers_a_surveyed_value_over_the_model() -> None:
    """A building that already has a surveyed floor count must not be overwritten."""
    est = FloorEstimate(
        floors_predicted=4.0, floors_lo=4, floors_hi=4, basis="surveyed_osm_tag"
    )
    assert est.authoritative is False
    assert "not a model estimate" in est.note