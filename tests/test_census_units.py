"""Census 2011 administrative-unit counts.

These assertions pin the official figures and, more importantly, the limits of
the release: it is a table of totals with no names, so it must never be used to
invent a place.
"""
from __future__ import annotations

import pytest

from app.pipelines import census_units


def test_published_national_totals():
    """The India-wide 2011 totals, as published."""
    counts = census_units.national_counts()["counts"]
    assert counts["districts"] == 640
    assert counts["sub_districts"] == 5924
    assert counts["statutory_towns"] == 4041
    assert counts["census_towns"] == 3894
    assert counts["villages"] == 640867


def test_maharashtra_matches_published_figures():
    entry = census_units.state_counts("Maharashtra")
    assert entry is not None
    assert entry["counts"]["districts"] == 35
    assert entry["counts"]["sub_districts"] == 355
    assert entry["counts"]["villages"] == 43663


def test_state_lookup_is_case_insensitive():
    assert census_units.state_counts("maharashtra") is not None
    assert census_units.state_counts("  MaHaRaShTra  ") is not None


def test_unknown_state_is_absent_not_zero():
    """A state outside the release must be missing, not a row of zeroes.

    'Not published' and 'this state has no districts' are different claims, and
    collapsing them would let a caller report an official zero for a place the
    census never covered.
    """
    assert census_units.state_counts("Atlantis") is None
    assert census_units.state_counts("") is None
    assert census_units.state_counts("Neverland") is None


def test_national_row_is_not_mistaken_for_a_state():
    """The 'India' row is a total, not a state, so it must not be listed as one."""
    names = census_units.state_names()
    assert "India" not in names
    assert len(names) == 35
    assert "Maharashtra" in names
    assert "Goa" in names


def test_release_carries_no_names_below_state_level():
    """The source is a counts table; the module must not pretend otherwise.

    If someone later adds a name column upstream, this fails and forces a
    decision about whether the API may then start naming places.
    """
    for entry in census_units._by_state().values():
        assert set(entry) == {"state", "census_year", "counts"}
        assert not any(k in entry for k in ("district_names", "villages", "talukas"))


def test_provenance_names_the_authority_and_the_gap():
    prov = census_units.PROVENANCE
    assert "Registrar General" in prov["source"]
    assert prov["license"].startswith("Government Open Data License")
    assert prov["census_year"] == 2011
    assert "place names" in prov["does_not_contain"].lower()


def test_counts_are_non_negative_ints_or_none():
    for name in census_units.state_names():
        entry = census_units.state_counts(name)
        for key, value in entry["counts"].items():
            assert value is None or (isinstance(value, int) and value >= 0), (name, key, value)
