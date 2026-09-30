"""Detect whether a floor-count label is an observation or a fabrication.

Added after ``national_twins`` turned out to be seeded by
``seed_mumbai_metropolitan.py`` with ``floors = random.randint(fl_min,
fl_max)`` over synthetic ``shapely_box`` footprints. A model trained on that
learns a random integer's relationship to rectangle size, which is why its R^2
of 0.25 looked plausible and meant nothing. Docstrings claiming the table held
"real OpenStreetMap-derived footprints" were simply wrong, and no accuracy
figure could have caught it because the data was internally consistent.

So the check is on the *label*, not on the accuracy.

The signal
----------
Real building storey counts are heavily right-skewed: most buildings are 1-3
storeys and the tail runs long. A uniform draw over a per-locality range
produces something structurally different: a few large spikes at the range
endpoints with near-empty counts between them, and almost no low-rise mass.

``entropy_ratio`` is the fraction of label entropy explained by the ten most
common values. A real distribution is spread thin; a uniform draw concentrates.
Combined with a spike ratio -- how much the largest bucket exceeds the median
non-empty bucket -- it separates the two without needing the seed script.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Sequence

# A real storey distribution puts most mass on low counts. If the modal value is
# the maximum of a narrow range and the low end is empty, it was drawn.
MIN_MODAL_SHARE = 0.12
MAX_LOW_TAIL_SHARE = 0.005


def audit_label_provenance(counts: Sequence[int]) -> dict[str, Any]:
    """Classify a floor-count column as observed, implausible, or indeterminate."""
    values = [int(v) for v in counts if v is not None]
    n = len(values)
    if n == 0:
        return {
            "verdict": "no_data",
            "usable_as_label": False,
            "reason": "no labels present",
        }

    counter = Counter(values)
    total = sum(counter.values())
    modal_value, modal_count = counter.most_common(1)[0]
    modal_share = modal_count / total

    lo, hi = min(values), max(values)
    span = hi - lo

    # Share of mass sitting on the lowest few storeys. Real: large. Uniform draw
    # over [a, b] with a > 1: ~zero.
    low_cut = lo + max(1, int(0.2 * span))
    low_share = sum(c for v, c in counter.items() if v <= low_cut) / total

    entropy = -sum((c / total) * math.log2(c / total) for c in counter.values())
    max_entropy = math.log2(len(counter)) if len(counter) > 1 else 1.0
    entropy_ratio = entropy / max_entropy if max_entropy else 0.0

    reasons: list[str] = []
    if modal_share >= 0.12 and low_share <= 0.005:
        reasons.append(
            f"{modal_share:.1%} of labels equal a single value ({modal_value}) and only "
            f"{low_share:.2%} fall in the lowest fifth of the observed range"
        )
    # Monotonicity is the discriminator that actually separates the two, and the
    # first attempt at this used bucket ratios, which does not work: a genuine
    # long thin tail also puts the largest bucket 50x above the median, so a
    # real distribution and a range draw both tripped it.
    #
    # Observed storey counts are right-skewed and therefore fall monotonically
    # with storey number. A value drawn from a range per locality is erratic:
    # large spikes separated by near-empty buckets, so the counts rise again
    # after falling. Counting those rises separates them cleanly.
    buckets = [counter.get(v, 0) for v in range(lo, hi + 1)]
    populated = sum(1 for b in buckets if b > 0)
    inversions = sum(1 for a, b in zip(buckets, buckets[1:]) if b > a * 1.5)
    inversion_rate = inversions / max(1, populated - 1) if populated > 1 else 0.0
    if populated >= 5 and inversion_rate >= 0.25:
        reasons.append(
            f"counts rise again after falling at {inversion_rate:.0%} of storey "
            "steps; observed buildings fall monotonically with storey number, "
            "while a value drawn from a range per locality spikes and dips"
        )

    # A perfectly even spread is also wrong: real storey counts are always
    # right-skewed, so near-maximal entropy across the range means the values
    # were spread uniformly rather than observed. This catches narrow uniform
    # draws that the monotonicity check cannot see, because a flat histogram
    # never falls and so never inverts.
    # The decisive signal, and the one that survives the weighted distribution.
    # Because the observed range is inflated by a long thin tail up to 65, the
    # shape tests above pass: 98% of mass sits in the lowest fifth, which looks
    # properly right-skewed. What gives it away is the *gaps*. Within the lower
    # part of the range, storey counts 3, 6, 8 and 10 carry six to thirteen
    # thousand buildings each while 4, 5 and 7 carry ten to forty. A uniform
    # draw per locality leaves exactly that pattern.
    #
    # Restricted to the lower half of the range and compared against the median
    # populated bucket, because a genuine distribution decays smoothly there
    # (tens of times over its first dozen values) while the draw varies by
    # hundreds. An earlier version compared across the whole range including the
    # tail and fired on a real distribution for that reason.
    mid = (lo + hi) // 2
    lower = [counter.get(v, 0) for v in range(lo, mid + 1)]
    lower_pop = sorted(b for b in lower if b > 0)
    if len(lower_pop) >= 4:
        med = lower_pop[len(lower_pop) // 2]
        if med > 0 and lower_pop[-1] / med >= 100:
            reasons.append(
                f"within storey values {lo}-{mid}, the largest bucket holds "
                f"{lower_pop[-1] / med:.0f}x the median populated bucket; a range "
                "draw leaves near-empty buckets between its spikes, which "
                "observed buildings do not"
            )

    if not reasons and entropy_ratio >= 0.95 and populated >= 4:
        reasons.append(
            f"counts are almost perfectly even across {populated} storey values "
            f"(entropy {entropy_ratio:.2f} of maximum); observed buildings are "
            "right-skewed, never uniform"
        )

    if reasons:
        return {
            "verdict": "implausible_for_observations",
            "usable_as_label": False,
            "n_labels": n,
            "modal_value": modal_value,
            "modal_share": round(modal_share, 4),
            "low_tail_share": round(low_share, 6),
            "entropy_ratio": round(entropy_ratio, 4),
            "inversion_rate": round(inversion_rate, 4),
            "reasons": reasons,
            "interpretation": (
                "This distribution is not consistent with observed buildings. It is "
                "consistent with a value drawn from a range, so any model trained on "
                "it learns the generator rather than the city."
            ),
        }

    return {
        "verdict": "consistent_with_observations",
        "usable_as_label": True,
        "n_labels": n,
        "modal_share": round(modal_share, 4),
        "low_tail_share": round(low_share, 6),
        "entropy_ratio": round(entropy_ratio, 4),
        "inversion_rate": round(inversion_rate, 4),
        "note": (
            "Shape is consistent with observed buildings. This says nothing about "
            "authority: a crowd-sourced or derived label can still be wrong."
        ),
    }