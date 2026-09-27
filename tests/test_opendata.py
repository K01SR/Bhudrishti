"""Regression tests for the open-data anywhere-on-Earth endpoints.

The provider chain is monkeypatched so tests are deterministic and run offline,
and the provider's own contract is checked separately in test_sources.py.
"""
from typing import Dict, Any

import pytest
from fastapi.testclient import TestClient

from app.opendata import service as opendata_service

_FIXTURE = {
    "buildings": [
        {
            "id": 777001,
            "name": "Test Tower",
            "height_m": 24.0,
            "floors": 7,
            "type": "tower",
            "ring_geo": [
                [72.9990, 19.0980], [72.9995, 19.0980], [72.9995, 19.0985],
                [72.9990, 19.0985], [72.9990, 19.0980],
            ],
            "center_geo": [72.99925, 19.09825],
        },
        {
            "id": 777002,
            "name": "Civic Hall",
            "height_m": 11.0,
            "floors": 3,
            "type": "commercial",
            "ring_geo": [
                [72.9975, 19.0990], [72.9980, 19.0990], [72.9980, 19.0994],
                [72.9975, 19.0994], [72.9975, 19.0990],
            ],
            "center_geo": [72.99775, 19.0992],
        },
    ],
    "labels": [
        {"name": "Test Plaza", "kind": "amenity", "lat": 19.09845, "lon": 72.99890},
    ],
    "fetched_at": "2026-01-01T00:00:00.000000+00:00",
}


def _fake_fetch(lat, lon, radius, max_buildings=220):
    """Stand-in provider returning a fixed, real-shaped payload."""
    from app.sources.base import AreaData, Provenance

    return AreaData(
        buildings=[dict(b) for b in _FIXTURE["buildings"]],
        labels=[dict(lb) for lb in _FIXTURE["labels"]],
        provenance=Provenance(
            provider="openstreetmap",
            dataset="test fixture",
            license="ODbL",
            source_url="https://www.openstreetmap.org/",
            authoritative=False,
            retrieved_at=_FIXTURE["fetched_at"],
        ),
    )


@pytest.fixture(autouse=True)
def _mock_overpass(monkeypatch: pytest.MonkeyPatch, tmp_path):
    # Patch the provider boundary: the service must never reach the network.
    monkeypatch.setattr(opendata_service, "fetch_area", _fake_fetch)
    # Keep the background refresher out of the way and isolate from any warmed
    # real-world cache on disk so the test is deterministic.
    monkeypatch.setattr(opendata_service, "_CACHE_PATH", str(tmp_path / "opendata_test_cache.json"))
    monkeypatch.setattr(opendata_service, "_last_refresh_ts", {})
    monkeypatch.setattr(opendata_service, "_worker_started", True)
    opendata_service._REGION_STORE.clear()


def test_opendata_area_returns_precinct_shaped_twins(client: TestClient):
    res = client.get("/api/v1/opendata/area", params={"lat": 19.0987, "lon": 72.9977, "radius": 400})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "openstreetmap"
    assert body["counts"]["buildings"] == 2
    assert body["center_local"] == [200.0, 200.0]

    b = body["buildings"][0]
    # Ids are namespaced by provider so a twin is traceable to its dataset.
    assert b["code"] == "OSM-777001"
    assert b["ulpin"] == "OSM-777001"
    assert b["name"] == "Test Tower"
    assert b["height_m"] == 24.0
    assert b["floors"] == 7
    assert b["height_basis"] == "source"
    # The area frame centres the whole set of buildings near the scene origin [200,200].
    all_x, all_y = [], []
    for eb in body["buildings"]:
        ring = eb["footprint_coords"]
        all_x.extend(p[0] for p in ring)
        all_y.extend(p[1] for p in ring)
    assert abs(sum(all_x) / len(all_x) - 200.0) < 25
    assert abs(sum(all_y) / len(all_y) - 200.0) < 25
    # Matching Geojson twin ring.
    assert b["footprint_geojson"]["coordinates"][0][0] == b["footprint_coords"][0]

    assert body["labels"][0]["name"] == "Test Plaza"
    # Cached second hit must not hit the (mocked) network again.
    res2 = client.get("/api/v1/opendata/area", params={"lat": 19.0987, "lon": 72.9977, "radius": 400})
    assert res2.json()["from_cache"] is True


def test_area_lidar_via_synthetic_ulpin(client: TestClient):
    res = client.get("/api/v1/lidar/pointcloud", params={"ulpin": "AREA-19.0987_72.9977_400"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["point_count"] > 0
    assert body["type"] == "area"
    assert body["ulpin"] == "AREA-19.0987_72.9977_400"
    classification_counts = [c["count"] for c in body["classifications"].values()]
    assert sum(classification_counts) == body["point_count"]


def test_area_lidar_binary_stream(client: TestClient):
    res = client.get("/api/v1/opendata/lidar/binary", params={"lat": 19.0987, "lon": 72.9977, "radius": 400})
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/octet-stream"
    point_count = int(res.headers["x-point-count"])
    assert point_count > 0
    assert len(res.content) == point_count * 32

def test_area_payload_carries_provenance(client: TestClient):
    """Real geometry must always ship with a traceable source record."""
    res = client.get("/api/v1/opendata/area", params={"lat": 19.0987, "lon": 72.9977, "radius": 400})
    assert res.status_code == 200, res.text
    body = res.json()
    prov = body["provenance"]
    assert prov["provider"] == "openstreetmap"
    assert prov["license"]
    assert prov["source_url"]
    # OpenStreetMap is community data, not an official publication.
    assert prov["authoritative"] is False
    assert prov["retrieved_at"]


def test_area_does_not_invent_compliance_values(client: TestClient):
    """A footprint source cannot yield permitted FSI or approval status."""
    res = client.get("/api/v1/opendata/area", params={"lat": 19.0987, "lon": 72.9977, "radius": 400})
    body = res.json()
    for b in body["buildings"]:
        assert b["fsi"] is None
        assert b["max_allowed_fsi"] is None
        assert b["fsi_status"] == "NOT_ASSESSED"
        assert b["units_count"] is None
        assert b["risk_level"] is None


def test_area_503_when_no_provider_is_reachable(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    """No source reachable must surface as an outage, never as generated data."""
    from app.sources import NoAuthenticSourceError

    def _boom(*args, **kwargs):
        raise NoAuthenticSourceError("all providers unreachable")

    monkeypatch.setattr(opendata_service, "fetch_area", _boom)
    opendata_service._REGION_STORE.clear()
    res = client.get("/api/v1/opendata/area", params={"lat": 19.0987, "lon": 72.9977, "radius": 400})
    assert res.status_code == 503
    # The operator gets the provider's own reason, not a fabricated payload.
    assert "unreachable" in res.json()["detail"]


def test_area_lidar_is_labelled_modelled(client: TestClient):
    """Generated points over real footprints must not claim to be a survey."""
    res = client.get("/api/v1/opendata/lidar", params={"lat": 19.0987, "lon": 72.9977, "radius": 400})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["data_type"] == "modelled_from_footprints"
    assert body["status"] == "MODELLED"
    assert body["source"] == "openstreetmap"


# ---- Conditional responses, sparse payloads, prewarm -----------------------

def test_area_sends_etag_and_honours_if_none_match(client: TestClient):
    """A repeat request for unchanged data must cost a 304, not the whole payload.

    The tag is derived from the serialised content rather than from `cached_at`,
    because the cache bookkeeping fields change on every read: folding them in
    would mint a fresh tag per request and make the mechanism useless.
    """
    params = {"lat": 19.0987, "lon": 72.9977, "radius": 400}
    first = client.get("/api/v1/opendata/area", params=params)
    assert first.status_code == 200, first.text
    etag = first.headers["etag"]
    assert etag
    assert "max-age" in first.headers.get("cache-control", "")

    second = client.get(
        "/api/v1/opendata/area",
        params=params,
        headers={"If-None-Match": etag},
    )
    assert second.status_code == 304
    assert second.content == b""
    assert second.headers["etag"] == etag

    # A caller holding a different payload still gets the body.
    stale = client.get(
        "/api/v1/opendata/area",
        params=params,
        headers={"If-None-Match": '"not-this-one"'},
    )
    assert stale.status_code == 200
    assert stale.json()["counts"]["buildings"] == 2


def test_etag_is_stable_across_a_cache_hit(client: TestClient):
    """The tag must describe the content, not the fact that it was cached."""
    params = {"lat": 19.0987, "lon": 72.9977, "radius": 400}
    cold = client.get("/api/v1/opendata/area", params=params)
    warm = client.get("/api/v1/opendata/area", params=params)
    assert warm.json()["from_cache"] is True
    assert cold.json()["from_cache"] is False
    assert cold.headers["etag"] == warm.headers["etag"]


def test_area_sparse_fields_keep_attribution(client: TestClient):
    """A caller wanting only counts should not download 220 buildings.

    Provenance and area attribution are never droppable: a sparse response that
    cannot be traced to a provider is worse than a large one.
    """
    params = {"lat": 19.0987, "lon": 72.9977, "radius": 400, "fields": "counts"}
    res = client.get("/api/v1/opendata/area", params=params)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["counts"]["buildings"] == 2
    assert body["provenance"]["provider"] == "openstreetmap"
    assert body["region"]
    assert body["area"]["lat"] == pytest.approx(19.0987)
    assert "buildings" not in body
    assert body["sparse_fields"] == ["counts"]

    # Asking for a field that does not exist says so rather than returning a
    # silently-empty area.
    typo = client.get("/api/v1/opendata/area", params={**{k: v for k, v in params.items() if k != "fields"}, "fields": "buildingz"})
    assert typo.status_code == 200
    assert typo.json()["unknown_fields"] == ["buildingz"]


# ---- One validator per representation ---------------------------------------

def test_render_mints_the_validator_from_the_body_it_returns():
    """`render` is the one place a representation and its tag are made together.

    Deriving the tag anywhere else is how the two drifted: the tag was computed
    from the full payload in one place while a different place projected the
    body. Here they are returned as a pair, so a caller cannot send one body
    under another's tag, and the tag is a function of the bytes that were
    selected rather than of the payload they were cut from.
    """
    payload = {
        "region": "19.0987_72.9977_r400",
        "area": {"lat": 19.0987, "lon": 72.9977},
        "source": "openstreetmap",
        "provenance": {"authoritative": False},
        "counts": {"buildings": 2, "labels": 1},
        "buildings": [{"code": "OSM-777001"}],
        "labels": [{"name": "Test Plaza"}],
        "from_cache": False,
        "cached_at": 1.0,
    }

    full_body, full_etag = opendata_service.render(payload)
    assert full_body is payload
    assert opendata_service.payload_etag(payload) == full_etag

    sparse_body, sparse_etag = opendata_service.render(payload, "counts")
    # The tag is the one for the body about to be sent, not for the whole area.
    assert sparse_etag == opendata_service.payload_etag(payload, "counts")
    assert sparse_etag != full_etag
    assert opendata_service.payload_etag(payload) == full_etag
    assert "buildings" not in sparse_body

    # Cache bookkeeping describes the read, not the area. Folding it in would
    # mint a fresh validator on every hit and make the mechanism pointless; it is
    # already surfaced as headers, so the body still carries it.
    cached = dict(payload, from_cache=True, cached_at=2.0)
    assert opendata_service.payload_etag(cached) == full_etag
    assert opendata_service.payload_etag(cached, "counts") == sparse_etag

    # Content that actually differs still moves the tag, or nothing would.
    moved = dict(payload, counts={"buildings": 3, "labels": 1})
    assert opendata_service.payload_etag(moved) != full_etag
    assert opendata_service.payload_etag(moved, "counts") != sparse_etag

    # A selection that adds nothing over the always-sent keys is its own
    # representation and is named as such, so it cannot alias the full body.
    _, default_etag = opendata_service.render(payload, "region")
    assert default_etag != full_etag


def test_full_and_sparse_representations_get_different_etags(client: TestClient):
    """An ETag names one representation, and a sparse body is a different one.

    The tag used to be computed over the full payload before `fields` was
    applied, so the full response and the sparse response for the same area
    shared it. A client caching the sparse body would present that shared tag,
    be told 304, and go on serving a payload stripped of every field it had
    never asked for -- believing the area had not changed when in fact it was
    holding the wrong bytes.
    """
    base = {"lat": 19.0987, "lon": 72.9977, "radius": 400}
    full = client.get("/api/v1/opendata/area", params=base)
    sparse = client.get("/api/v1/opendata/area", params={**base, "fields": "counts"})
    assert full.status_code == 200 and sparse.status_code == 200

    assert full.headers["etag"] != sparse.headers["etag"]

    # Two different sparse selections are two different representations too.
    labels = client.get("/api/v1/opendata/area", params={**base, "fields": "labels"})
    assert labels.headers["etag"] != sparse.headers["etag"]
    assert labels.headers["etag"] != full.headers["etag"]

    # The response says which representation the tag names, so a cache holding
    # more than one can tell them apart.
    assert full.headers["x-opendata-representation"] == "full"
    assert sparse.headers["x-opendata-representation"] == "sparse"


def test_etag_ignores_field_order_not_content(client: TestClient):
    """The tag is a function of what was selected, not of how it was spelled.

    `fields=counts,labels` and `fields=labels,counts` ask for the same
    representation, so they must hash alike; a client that reorders the query on
    a retry would otherwise be handed a fresh body for an unchanged area.
    """
    base = {"lat": 19.0987, "lon": 72.9977, "radius": 400}
    a = client.get("/api/v1/opendata/area", params={**base, "fields": "counts,labels"})
    b = client.get("/api/v1/opendata/area", params={**base, "fields": "labels,counts"})
    c = client.get("/api/v1/opendata/area", params={**base, "fields": " labels , counts "})
    assert a.status_code == b.status_code == c.status_code == 200
    assert a.headers["etag"] == b.headers["etag"] == c.headers["etag"]


def test_if_none_match_is_answered_per_representation(client: TestClient):
    """A 304 may only go to a client holding exactly the body on offer.

    The full response, the sparse response and a *different* sparse response are
    three separate conditional exchanges. Holding one must not validate against
    another, in either direction.
    """
    base = {"lat": 19.0987, "lon": 72.9977, "radius": 400}
    full_etag = client.get("/api/v1/opendata/area", params=base).headers["etag"]
    sparse = client.get("/api/v1/opendata/area", params={**base, "fields": "counts"})
    sparse_etag = sparse.headers["etag"]
    labels = client.get("/api/v1/opendata/area", params={**base, "fields": "labels"})
    labels_etag = labels.headers["etag"]

    # Each representation revalidates against its own tag.
    for params, tag in (
        (base, full_etag),
        ({**base, "fields": "counts"}, sparse_etag),
        ({**base, "fields": "labels"}, labels_etag),
    ):
        hit = client.get("/api/v1/opendata/area", params=params, headers={"If-None-Match": tag})
        assert hit.status_code == 304, (params, hit.text)
        assert hit.headers["etag"] == tag
        assert hit.content == b""

    # Holding the sparse body must NOT validate against the full representation.
    cross = client.get("/api/v1/opendata/area", params=base, headers={"If-None-Match": sparse_etag})
    assert cross.status_code == 200
    assert "buildings" in cross.json()

    # Nor the other way round: the sparse body has to come back in full.
    cross2 = client.get(
        "/api/v1/opendata/area",
        params={**base, "fields": "counts"},
        headers={"If-None-Match": full_etag},
    )
    assert cross2.status_code == 200
    assert cross2.json()["sparse_fields"] == ["counts"]

    # And a third sparse selection is not answered by either of the first two.
    for tag in (full_etag, sparse_etag):
        assert client.get(
            "/api/v1/opendata/area", params={**base, "fields": "labels"}, headers={"If-None-Match": tag}
        ).status_code == 200


def test_if_none_match_uses_weak_comparison_and_lists(client: TestClient):
    """`If-None-Match` is defined with weak comparison, so W/ must still match."""
    base = {"lat": 19.0987, "lon": 72.9977, "radius": 400}
    full = client.get("/api/v1/opendata/area", params=base)
    etag = full.headers["etag"]

    weak = client.get("/api/v1/opendata/area", params=base, headers={"If-None-Match": f"W/{etag}"})
    assert weak.status_code == 304

    # A list of validators: a match anywhere in the list is a match.
    listed = client.get(
        "/api/v1/opendata/area",
        params=base,
        headers={"If-None-Match": f'"something-else", W/{etag}'},
    )
    assert listed.status_code == 304

    # `*` means "I hold whatever you have", which is a 304 for a resource that
    # exists -- and it must not leak a tag for a representation not on offer.
    star = client.get("/api/v1/opendata/area", params={**base, "fields": "counts"}, headers={"If-None-Match": "*"})
    assert star.status_code == 304
    assert star.headers["etag"] != etag


def test_prewarm_warms_through_the_same_cache(client: TestClient):
    """Prewarming moves the fetch earlier; it does not change what is served."""
    res = client.post("/api/v1/opendata/prewarm", params={"areas": "19.0987,72.9977,400"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["configured"] == 1
    assert body["warmed"] == 1
    assert body["failed"] == 0

    served = client.get("/api/v1/opendata/area", params={"lat": 19.0987, "lon": 72.9977, "radius": 400})
    assert served.json()["from_cache"] is True

    again = client.post("/api/v1/opendata/prewarm", params={"areas": "19.0987,72.9977,400"})
    assert again.json()["already_cached"] == 1


def test_prewarm_reports_failures_without_raising(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    """One unreachable region must not abort the batch or take the process down."""
    def _boom(*args, **kwargs):
        raise RuntimeError("provider unreachable")

    monkeypatch.setattr(opendata_service, "fetch_area", _boom)
    opendata_service._REGION_STORE.clear()
    res = client.post("/api/v1/opendata/prewarm", params={"areas": "19.0987,72.9977,400;garbage"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["failed"] == 2
    assert body["warmed"] == 0
    assert all("reason" in r for r in body["regions"])


def test_prewarm_reads_the_configured_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENDATA_PREWARM_AREAS", "")
    assert opendata_service.prewarm_areas_from_env()["source"] == "unset"
    monkeypatch.setenv("OPENDATA_PREWARM_AREAS", "19.0987,72.9977,400")
    result = opendata_service.prewarm_areas_from_env()
    assert result["source"] == "OPENDATA_PREWARM_AREAS"
    assert result["warmed"] == 1


def test_prewarm_areas_is_optional_and_falls_back_to_the_configured_set(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    """`areas` is documented as optional, so omitting it must warm what is configured.

    The endpoint required the parameter while its own description said "Omit to
    use OPENDATA_PREWARM_AREAS", so the documented fallback was unreachable: the
    request was rejected before any of it ran. The response names which of the
    two inputs was used, because "warmed" alone cannot tell a caller whether it
    just warmed its own list or the deployment's.
    """
    monkeypatch.setenv("OPENDATA_PREWARM_AREAS", "19.0987,72.9977,400")

    res = client.post("/api/v1/opendata/prewarm")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "OPENDATA_PREWARM_AREAS"
    assert body["configured"] == 1
    assert body["warmed"] == 1

    # Same cache, same providers: the configured area is now warm.
    served = client.get("/api/v1/opendata/area", params={"lat": 19.0987, "lon": 72.9977, "radius": 400})
    assert served.json()["from_cache"] is True

    # A blank value is the same as omitting it, not an empty batch.
    blank = client.post("/api/v1/opendata/prewarm", params={"areas": "   "})
    assert blank.status_code == 200
    assert blank.json()["source"] == "OPENDATA_PREWARM_AREAS"
    assert blank.json()["already_cached"] == 1

    # An explicit list still wins over the configured one, and says so.
    explicit = client.post("/api/v1/opendata/prewarm", params={"areas": "19.0960,72.9950,300"})
    assert explicit.status_code == 200, explicit.text
    assert explicit.json()["source"] == "request:areas"
    assert explicit.json()["warmed"] == 1


def test_prewarm_fails_clearly_when_nothing_is_nominated(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    """Neither the request nor the deployment nominates an area: say so.

    Reporting a zero-count batch would read as a warm-up that had nothing to do,
    which is a different claim from "this deployment nominates nothing". The two
    causes are separated so the operator can tell which one to fix.
    """
    opendata_service._REGION_STORE.clear()
    monkeypatch.setenv("OPENDATA_PREWARM_AREAS", "")
    res = client.post("/api/v1/opendata/prewarm")
    assert res.status_code == 400, res.text
    detail = res.json()["detail"]
    assert "OPENDATA_PREWARM_AREAS" in detail
    assert "Nothing was fetched" in detail

    # Set, but holding no entry at all -- a different mistake, said differently.
    monkeypatch.setenv("OPENDATA_PREWARM_AREAS", " ; ")
    empty = client.post("/api/v1/opendata/prewarm")
    assert empty.status_code == 400, empty.text
    assert "holds no" in empty.json()["detail"]

    # Nothing was warmed while refusing.
    assert opendata_service._REGION_STORE == {}


def test_prewarm_fallback_reports_failures_from_the_configured_set(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    """A configured area that cannot be fetched is reported, not swallowed."""
    def _boom(*args, **kwargs):
        raise RuntimeError("provider unreachable")

    monkeypatch.setattr(opendata_service, "fetch_area", _boom)
    opendata_service._REGION_STORE.clear()
    monkeypatch.setenv("OPENDATA_PREWARM_AREAS", "19.0987,72.9977,400")
    res = client.post("/api/v1/opendata/prewarm")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "OPENDATA_PREWARM_AREAS"
    assert body["warmed"] == 0
    assert body["failed"] == 1
    assert "provider unreachable" in body["regions"][0]["reason"]
