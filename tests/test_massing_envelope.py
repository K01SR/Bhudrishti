"""The massing envelope must be renderable without implying a floor plate.

The seed gives every level the same footprint, so the six
``architecture.slabs`` plates are geometrically identical. That is fine as
architectural decoration but it reads as "each storey has this exact outline",
and no survey in this system records an individual storey's plan. These tests
pin the distinction: the envelope exists, it is built from real elevations, and
it says in the payload that it is not a floor plate.

If someone later gets real per-storey outlines, the honest change is to stop
using this block and serve the surveyed plates -- so one test asserts the
labels are still present, and its failure message says that.
"""
from __future__ import annotations

import pytest

from app.scene.scene_architect import _massing_envelope

FOOTPRINT = [[145.0, 144.0], [175.0, 144.0], [175.0, 161.0], [145.0, 161.0]]


def _levels() -> list[dict]:
    return [
        {"level_code": "B1", "level_type": "BASEMENT", "min_z": -3.5, "max_z": 0.0},
        {"level_code": "G", "level_type": "GROUND", "min_z": 0.0, "max_z": 3.6},
        {"level_code": "L01", "level_type": "HABITABLE", "min_z": 3.6, "max_z": 7.2},
        {"level_code": "L04", "level_type": "HABITABLE", "min_z": 14.4, "max_z": 18.0},
    ]


def test_envelope_covers_every_level_with_its_real_z_band() -> None:
    env = _massing_envelope(FOOTPRINT, _levels())
    assert env["available"] is True
    assert len(env["levels"]) == 4
    for box, lv in zip(env["levels"], _levels()):
        assert box["level_code"] == lv["level_code"]
        assert box["min_z"] == lv["min_z"]
        assert box["max_z"] == lv["max_z"]
        assert box["height_m"] == pytest.approx(lv["max_z"] - lv["min_z"], abs=0.01)


def test_envelope_basement_is_below_ground() -> None:
    """A basement at negative Z is the level most likely to be dropped by a renderer."""
    env = _massing_envelope(FOOTPRINT, _levels())
    basement = env["levels"][0]
    assert basement["level_code"] == "B1"
    # The band runs up *to* ground rather than through it, so the comparison is
    # <= and not <.
    assert basement["min_z"] < 0, "basement must start below the datum"
    assert basement["max_z"] <= 0, "basement must not rise above the datum"


def test_envelope_declares_it_is_not_a_floor_plate() -> None:
    """The label is the point. Remove it and this test should fail."""
    env = _massing_envelope(FOOTPRINT, _levels())
    assert env["is_massing_envelope"] is True
    assert env["not_a_floor_plate"], (
        "the payload must keep saying these boxes are not surveyed storey outlines; "
        "if real per-storey geometry now exists, serve that instead of this block"
    )
    assert env["plan_basis"] == "declared_structure_footprint"
    assert env["elevation_basis"] == "level_min_max_z"


def test_envelope_states_its_coordinate_frame() -> None:
    """Local metres under a degrees label is a bug that has happened here before.

    ``structure.footprint_ring``, ``architecture.slabs`` and
    ``units[].mesh_3d`` are all in the generator's local metre frame while their
    column is nominally geojson. Anything a renderer might map must be able to
    see that from the payload alone.
    """
    env = _massing_envelope(FOOTPRINT, _levels())
    assert env["frame"] == "local_metres"
    assert "not lon/lat" in env["frame_note"]


def test_envelope_area_matches_the_declared_footprint() -> None:
    env = _massing_envelope(FOOTPRINT, _levels())
    # 30m x 17m, and the parcel is 40 x 25, so the building sits inside its plot.
    assert env["footprint_area_m2"] == pytest.approx(510.0, abs=0.01)


def test_envelope_is_unavailable_rather_than_empty_when_it_cannot_be_built() -> None:
    """No footprint means no envelope. It must not silently return zero boxes."""
    env = _massing_envelope([], _levels())
    assert env["available"] is False
    assert env["levels"] == []
    assert env["reason"]

    env2 = _massing_envelope(FOOTPRINT, [])
    assert env2["available"] is False
    assert env2["reason"]


def test_envelope_boxes_share_the_declared_footprint_not_per_level_shapes() -> None:
    """All boxes span the same plan span, which is exactly the caveat being made.

    If this ever changes because real storey outlines arrived, the
    ``not_a_floor_plate`` label becomes wrong and must be revisited with it.
    """
    env = _massing_envelope(FOOTPRINT, _levels())
    spans = {(b["min_x"], b["min_y"], b["max_x"], b["max_y"]) for b in env["levels"]}
    assert len(spans) == 1, "storey outlines now differ; revisit the envelope's labelling"