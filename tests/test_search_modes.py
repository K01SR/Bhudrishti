"""Global search must be able to return real places without the generated index.

The original design mixed two different questions in one list: "where is this
place" (answered by the real LGD gazetteer) and "which parcel/ULPIN is this"
(answered entirely by generated PostGIS rows and pilot assets). A caller had to
read a provenance field on every row to know which one it was looking at, which
means a UI that forgets to check will confidently fly a user to a fabricated
boundary and call it real.

These tests pin the `mode` split: `places` returns only the gazetteer and
declares itself non-mixed, `records` excludes the gazetteer, and `all` still
behaves as before for existing callers.
"""
from __future__ import annotations

import inspect

import pytest

from app.api.v1 import search as search_api


def _mode_param():
    params = inspect.signature(search_api.search).parameters
    assert "mode" in params, "search() must accept an explicit mode"
    return params["mode"]


def _mode_default() -> str:
    """FastAPI wraps Query defaults; tests want the value the caller gets."""
    default = _mode_param().default
    return getattr(default, "default", default)


def test_search_exposes_a_mode_parameter():
    assert _mode_default() == "all", "existing callers must keep working unchanged"


def test_mode_pattern_rejects_unknown_values():
    assert _mode_default() in ("all", "places", "records")


@pytest.mark.asyncio
async def test_places_mode_returns_only_the_real_gazetteer():
    response = await search_api.search(q="Airoli", limit=25, mode="places")

    assert response["mode"] == "places"
    assert response["is_mixed_provenance"] is False
    assert response["real_sources"] == ["lgd"]
    assert response["results"], "the real gazetteer should still answer for a real village name"
    for row in response["results"]:
        assert row["source"] == "lgd", f"non-gazetteer row leaked into places mode: {row}"


@pytest.mark.asyncio
async def test_places_mode_never_returns_a_generated_row():
    # A pilot unit code matches the generated hero parcel. In places mode that
    # row must not appear at all, rather than appearing and being labelled.
    response = await search_api.search(q="B-17", limit=25, mode="places")
    assert all(row["source"] == "lgd" for row in response["results"])


@pytest.mark.asyncio
async def test_places_mode_empty_query_does_not_fall_back_to_generated_landmarks():
    response = await search_api.search(q="", limit=25, mode="places")
    assert response["results"] == [], "an empty places query has no real answer to give"


@pytest.mark.asyncio
async def test_records_mode_excludes_the_real_gazetteer():
    response = await search_api.search(q="Airoli", limit=25, mode="records")
    assert all(row.get("source") != "lgd" for row in response["results"])


@pytest.mark.asyncio
async def test_all_mode_still_declares_itself_mixed():
    response = await search_api.search(q="Airoli", limit=25, mode="all")
    assert response["mode"] == "all"
    assert response["is_mixed_provenance"] is True


@pytest.mark.asyncio
async def test_every_response_reports_the_mode_it_ran_in():
    for mode in ("all", "places", "records"):
        response = await search_api.search(q="Nerul", limit=5, mode=mode)
        assert response["mode"] == mode

@pytest.mark.asyncio
async def test_boundary_rows_declare_whether_their_geometry_is_real():
    """A generated subdivision must not read as an official boundary.

    `admin_boundaries` mixes real geoBoundaries ADM1/ADM2 geometry with
    grid-synthesised TALUKA and VILLAGE subdivisions. Search used to render both
    as "Admin Code: ...", which let a generated subdivision present itself as an
    official boundary.
    """
    from app.api.v1 import search as search_module

    response = await search_module.search(q="Maharashtra", limit=25, mode="all")
    boundaries = [r for r in response["results"] if r.get("kind") == "jurisdiction"]
    for row in boundaries:
        assert "source" in row, f"boundary row hides its provenance: {row}"
        assert "authoritative" in row, f"boundary row hides whether it is real: {row}"
        assert "data_provenance" in row
        if row["source"] == "synthetic":
            assert row["authoritative"] is False
            assert row["data_provenance"] == "demo-generated"
            assert row.get("geometry_note"), "a synthetic boundary must say what it is"
        else:
            assert row["authoritative"] is True
