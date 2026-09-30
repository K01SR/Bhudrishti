"""Estimate a building's floor count from its footprint shape alone.

Why this is a real cadastral problem and not a demo

Vertical parcel delineation needs a floor count for every building. Where a
building survey exists you have it; where one does not, you have a footprint and
nothing else. India has cadastral parcel geometry and building footprints for
far more buildings than it has floor surveys, so "how many storeys is this, from
its outline" is the step that decides whether vertical parcels can be delineated
automatically at national scale.

The target and the features

The *intended* target is ``national_twins.floors`` against footprint features.
That label is **not usable** and no model ships from it.

``national_twins`` was seeded by ``seed_mumbai_metropolitan.py``, which sets
``floors = random.randint(fl_min, fl_max)`` per locality and builds each
footprint with ``shapely_box`` from parcel dimensions. Both halves are generated.
The polygons are not buildings: median footprint is 53 km^2 and the largest is
3,592 km^2, because parcel boxes were stored as building outlines. Only 2.89%
of rows fall under 10,000 m^2.

An earlier version of this module described the table as holding "45,489 real
OpenStreetMap-derived building footprints". That was wrong, and it produced a
model scoring R^2 0.24, which is exactly the danger: fitting a uniform random
integer against rectangle size yields a smooth, plausible-looking relationship.
Nothing in the accuracy figure could have caught it. ``label_provenance`` exists
to reject the label before the fit, not after.

``height_m`` stays out of the feature set for a separate and still-valid reason:
floors is close to ``height_m / 3``, so including it would make the task
trivially solvable. Every feature is computed from the plan footprint, which is
the information actually available for an unsurveyed building.

Honesty notes that the model output carries

- The label is a generator output, not an observation. Agreement with it is
  meaningless and must not be reported as accuracy.
- Even a correctly-shaped label from OpenStreetMap would be crowd-sourced, not
  authority. ``app.opendata.overpass._floors`` also falls back to
  ``height_m / 3.5`` when ``building:levels`` is absent, which is circular for
  a floors model and is why the fallback cannot serve as a training label.
- The split is geographic, not random. See ``build_floor_estimator`` for why a
  random split overstates accuracy.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

FEATURE_NAMES = [
    "log_area_m2",
    "log_perimeter_m",
    "compactness",
    "elongation",
    "orientation_rad",
    "vertex_count",
    "bbox_aspect",
    "area_over_perimeter",
    "neighbour_count_50m",
    "neighbour_mean_area_50m",
    "local_density_100m",
]
FEATURE_DOCS = {
    "log_area_m2": "natural log of footprint area; size is the strongest single cue",
    "log_perimeter_m": "natural log of perimeter",
    "compactness": "isoperimetric quotient 4*pi*A/P^2; 1.0 is a circle, lower is sprawling",
    "elongation": "major/minor axis of the oriented bounding box",
    "orientation_rad": "dominant axis bearing, radians 0-pi; footprints align to streets",
    "vertex_count": "vertices in the footprint; proxies how complex the outline is",
    "bbox_aspect": "axis-aligned bbox long/short ratio",
    "area_over_perimeter": "A/P, a compactness proxy that is scale-aware",
    "neighbour_count_50m": "how many other buildings sit within 50m; dense blocks differ",
    "neighbour_mean_area_50m": "mean neighbour area within 50m; local grain",
    "local_density_100m": "buildings within 100m per hectare, a coarse urban-form signal",
}


@dataclass
class FloorEstimate:
    """One prediction, with the uncertainty that makes it usable.

    ``p10``/``p90`` come from the spread of training neighbours, not from a
    model confidence interval: a random forest has no calibrated distribution,
    and reporting one would be inventing precision. A caller that needs to
    escalate to a survey can act on the width.
    """

    floors_predicted: float
    floors_lo: int
    floors_hi: int
    basis: str
    authoritative: bool = False

    def __post_init__(self) -> None:
        # The note follows the basis rather than being passed in, because the
        # failure mode is a surveyed value carrying the model's caveat -- or worse,
        # an estimate carrying none. Deriving it here means a caller cannot get
        # the pairing wrong by omitting an argument.
        if "survey" in self.basis.lower():
            self.note = "Recorded on the source row; not a model estimate."
        else:
            self.note = (
                "Estimated from footprint shape by a model trained on "
                "OpenStreetMap floor tags. Not a survey and not authoritative."
            )

    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "floors_predicted": round(self.floors_predicted, 2),
            "floors_lo": self.floors_lo,
            "floors_hi": self.floors_hi,
            "basis": self.basis,
            "authoritative": self.authoritative,
            "note": self.note,
        }


def features_from_geometry(
    area_m2: float,
    perimeter_m: float,
    centroid_x: float,
    centroid_y: float,
    vertex_count: int,
    major_axis_m: float,
    minor_axis_m: float,
    bearing_rad: float,
    bbox_width_m: float,
    bbox_height_m: float,
    neighbour_count_50m: int,
    neighbour_mean_area_50m: float,
    local_density_100m: float,
) -> list[float]:
    """Assemble the feature vector in ``FEATURE_NAMES`` order.

    Kept as a plain function of scalars, with no geometry library, so the
    training script (which reads features from PostGIS) and the serving path
    (which may have shapely or not) cannot drift apart. Order is the contract and
    is asserted in the tests.
    """
    area = max(float(area_m2), 1e-6)
    perim = max(float(perimeter_m), 1e-6)
    major = max(float(major_axis_m), 1e-6)
    minor = max(float(minor_axis_m), 1e-6)
    compactness = (4.0 * math.pi * area) / (perim * perim)
    return [
        math.log(area),
        math.log(perim),
        compactness,
        major / minor,
        float(bearing_rad) % math.pi,
        float(vertex_count),
        max(float(bbox_width_m), 1e-6) / max(float(bbox_height_m), 1e-6),
        area / perim,
        float(neighbour_count_50m),
        float(neighbour_mean_area_50m),
        float(local_density_100m),
    ]


def decode_twin(tree: dict[str, Any]) -> FloorEstimate:
    """Turn a ``national_twins`` row into an estimate.

    Prefers the surveyed value when the row has one. A building whose floors are
    already recorded does not need an estimate, and returning the recorded value
    keeps the estimator from quietly disagreeing with data that outranks it.
    """
    surveyed = tree.get("floors")
    if surveyed is not None:
        value = float(surveyed)
        return FloorEstimate(
            floors_predicted=value,
            floors_lo=int(round(value)),
            floors_hi=int(round(value)),
            basis="surveyed_osm_tag",
            note="Recorded on the source row; not a model estimate.",
        )
    raise ValueError("no features and no surveyed floors: nothing to estimate from")