"""Label provenance: the check that has to run before a model is fitted.

``national_twins.floors`` turned out to be ``random.randint(fl_min, fl_max)``
per locality, seeded by ``seed_mumbai_metropolitan.py`` over ``shapely_box``
footprints. A RandomForest fitted to that reached R2 0.24 with a MAE of 2.1
floors, which read as a mediocre-but-real model. It was fitting a generator.

These tests pin the detector and the refusal, because the dangerous case is not
an obviously broken dataset, it is a plausible one. The synthetic distribution
is deliberately realistic in every respect a metric would look at.
"""
from __future__ import annotations

from app.ml.label_provenance import audit_label_provenance

# A genuine storey distribution: right-skewed, heavy mass on low counts.
REALISTIC = (
    [1] * 3000
    + [2] * 2000
    + [3] * 1200
    + [4] * 400
    + [5] * 200
    + [6] * 100
    + [7] * 60
    + [8] * 30
    + [9] * 20
    + [10] * 10
    + [11] * 5
    + [12] * 3
    + [15] * 2
    + [20] * 1
)

# The real national_twins shape, read from the database: spikes at 3, 6, 8, 10
# with tens-to-low-thousands between, plus a thin tail out to 65. The tail has
# to be present for the bucket-gap signal to fire -- truncated at 14 the range
# collapses and the detector falls through to the monotonicity signal instead,
# which is why this fixture mirrors the real 3-65 span rather than a tidy
# 13-value summary.
SYNTHETIC_RANGE_DRAW = (
    [3] * 6463
    + [6] * 12583
    + [8] * 12613
    + [10] * 12784
    + [4] * 10
    + [5] * 14
    + [7] * 20
    + [9] * 40
    + [11] * 34
    + [12] * 40
    + [13] * 42
    + [14] * 45
    + [15] * 48
    + [16] * 44
    + [17] * 40
    + [18] * 36
    + [19] * 33
    + [20] * 30
    + [21] * 27
    + [22] * 25
    + [23] * 22
    + [24] * 20
    + [25] * 18
    + [26] * 16
    + [27] * 15
    + [28] * 13
    + [29] * 12
    + [30] * 11
    + [31] * 10
    + [32] * 9
    + [33] * 8
    + [34] * 7
    + [35] * 6
    + [36] * 6
    + [37] * 5
    + [38] * 5
    + [39] * 4
    + [40] * 4
    + [41] * 3
    + [42] * 3
    + [43] * 3
    + [42] * 2
)


def test_right_skewed_distribution_is_accepted():
    """A real storey distribution must not be flagged, or the gate is useless."""
    result = audit_label_provenance(REALISTIC)
    assert result["verdict"] == "consistent_with_observations"
    assert result["usable_as_label"] is True


def test_uniform_range_draw_is_rejected():
    """This is the national_twins label. It must be refused."""
    result = audit_label_provenance(SYNTHETIC_RANGE_DRAW)
    assert result["verdict"] == "implausible_for_observations"
    assert result["usable_as_label"] is False
    assert result["reasons"], "a rejection must explain itself"


def test_rejection_cites_the_bucket_gap():
    """The reason has to name the observable evidence, not just assert a verdict.

    The shape tests alone pass on this data: 98% of mass sits in the lowest
    fifth of the 3-65 range, which looks properly right-skewed. What exposes it
    is the 336x gap between the largest and median populated bucket in the lower
    half of the range, so that specific signal must appear in the explanation.
    """
    result = audit_label_provenance(SYNTHETIC_RANGE_DRAW)
    joined = " ".join(result["reasons"]).lower()
    assert "largest bucket" in joined and "median populated bucket" in joined


def test_flat_distribution_is_rejected():
    """A perfectly even spread is also not a building distribution."""
    result = audit_label_provenance([5] * 1000 + [7] * 1000 + [9] * 1000 + [11] * 1000)
    assert result["usable_as_label"] is False


def test_wide_uniform_draw_is_rejected():
    """Uniform across a wide range, not just a narrow one."""
    result = audit_label_provenance([3] * 900 + [20] * 900 + [40] * 900 + [60] * 900)
    assert result["usable_as_label"] is False


def test_empty_label_is_not_usable():
    assert audit_label_provenance([])["usable_as_label"] is False


def test_shape_alone_never_claims_authority():
    """Even a passing shape check must not imply the label is authoritative."""
    result = audit_label_provenance(REALISTIC)
    assert result["usable_as_label"] is True
    assert "right" in result["note"].lower() or "not" in result["note"].lower()
    assert "authority" in result["note"].lower()


def test_serving_is_gated_on_the_audit(monkeypatch):
    """A model on disk must not be served while the audit fails.

    This is the gate that matters at runtime: a fitted artefact existed from the
    retracted run, so an audit-only check that nobody calls would leave it
    loadable and serving fabricated survey prioritisation.
    """
    from app.ml import floor_triage

    monkeypatch.setattr(floor_triage, "AUDIT_PATH", floor_triage.ARTIFACT_DIR / "does_not_exist.json")
    assert floor_triage.load_label_provenance_audit()["usable_as_label"] is False
    assert floor_triage.load_model() is None