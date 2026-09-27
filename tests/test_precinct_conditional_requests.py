"""/precinct/buildings must support conditional requests.

The payload is ~364 KB and identical on every call until the dataset changes,
while the map refetches it on every pan. An ETag lets the client revalidate for
the price of a 304 instead of a 364 KB body.

The ETag content is asserted, not just its presence: a validator that changes
when the body changes is the only thing that makes revalidation safe.
"""

import sys

import pytest
from fastapi.testclient import TestClient

from app.main import app

BUILDINGS = "/api/v1/precinct/buildings"


@pytest.fixture
def client():
    return TestClient(app)


def _headers():
    """Demo-gated group, so demo mode must be on for any of this to answer."""
    from app.core.config import settings

    if not getattr(settings, "ENABLE_DEMO_MODE", False):
        pytest.skip("precinct routes are demo-gated")


def test_first_request_returns_an_etag(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    _headers()
    r = client.get(BUILDINGS)
    assert r.status_code == 200
    etag = r.headers.get("etag")
    assert etag, "a conditional-request validator must be present"
    assert etag.startswith('"') and etag.endswith('"')


def test_matching_etag_returns_304_with_no_body(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    _headers()
    etag = client.get(BUILDINGS).headers["etag"]
    r = client.get(BUILDINGS, headers={"If-None-Match": etag})
    assert r.status_code == 304
    assert r.content == b"", "a 304 must not carry a body"
    # The validator must come back so the client can keep it.
    assert r.headers.get("etag") == etag


def test_stale_etag_returns_the_full_body(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    _headers()
    r = client.get(BUILDINGS, headers={"If-None-Match": '"not-the-current-tag"'})
    assert r.status_code == 200
    assert r.content, "a stale validator must not be answered with 304"


def test_wildcard_matches(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    _headers()
    r = client.get(BUILDINGS, headers={"If-None-Match": "*"})
    assert r.status_code == 304


def test_weak_comparison_is_honoured(client, monkeypatch):
    """If-None-Match uses weak comparison, so W/"x" must match "x"."""
    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    _headers()
    etag = client.get(BUILDINGS).headers["etag"]
    r = client.get(BUILDINGS, headers={"If-None-Match": f"W/{etag}"})
    assert r.status_code == 304


def test_etag_among_several_candidates(client, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    _headers()
    etag = client.get(BUILDINGS).headers["etag"]
    r = client.get(BUILDINGS, headers={"If-None-Match": f'"other", {etag}, "third"'})
    assert r.status_code == 304


def test_cache_control_forbids_serving_stale_geometry(client, monkeypatch):
    """no-cache, not max-age: the geometry behind this payload is repairable."""
    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    _headers()
    r = client.get(BUILDINGS)
    cc = r.headers.get("cache-control", "")
    assert "no-cache" in cc
    assert "max-age" not in cc, (
        "a max-age would let a browser serve a stale shape for the whole window "
        "after repair_parcel_geometry rewrites parcels.geom"
    )


def test_etag_tracks_content_not_time(client, monkeypatch):
    """Repeated identical responses must reuse one tag, or nothing is cached."""
    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    _headers()
    a = client.get(BUILDINGS)
    b = client.get(BUILDINGS)
    assert a.headers["etag"] == b.headers["etag"]
    assert a.content == b.content


def test_internal_callers_do_not_go_through_the_route_handler():
    """The route takes (response, request); internal callers must not.

    Adding those parameters to a function that eight other call sites invoke
    would raise TypeError at runtime, in code paths no status-code assertion in
    this file would necessarily touch.
    """
    import inspect

    from app.api.v1.precinct import _precinct_buildings_payload, get_precinct_buildings

    assert list(inspect.signature(get_precinct_buildings).parameters) == ["response", "request"]
    assert list(inspect.signature(_precinct_buildings_payload).parameters) == []

    source = inspect.getsource(sys.modules["app.api.v1.precinct"])
    assert "_precinct_buildings_payload()" in source
    # No module may call the route handler directly.
    assert "get_precinct_buildings()" not in source

    for mod in ("app.api.v1.osm", "app.api.v1.ids"):
        text = inspect.getsource(sys.modules[mod])
        assert "get_precinct_buildings()" not in text, mod


def test_sibling_routes_still_serve(client, monkeypatch):
    """The extraction must not have broken the routes that consume the payload."""
    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    _headers()
    assert client.get("/api/v1/precinct/units").status_code == 200
    assert client.get("/api/v1/precinct/buildings/B-17").status_code == 200
