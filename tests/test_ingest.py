"""Ingestion endpoints: derived data must be labelled, and bad input refused.

Every capability under test here can produce geometry, so each test pins the
part that is easy to get quietly wrong: that a degree value is never treated as
a metre, that coordinates outside the country are refused rather than stored,
that a derived point cloud is never reported as survey data, and that an
oversized upload is rejected before it is buffered.

Authentication is done with the real login flow, the same as every other
authenticated test in this suite. An earlier version of this file called the
endpoints unauthenticated and one attempt to fix that introduced a global
`TESTING=true` auth bypass in app/core/security.py; that granted every caller
STATE_ADMIN and is not how a test is allowed to authenticate.
"""
import io

import pytest

# A ~1km x 1km box near Mumbai. Degrees, not metres: the difference the whole
# module turns on.
MUMBAI_SQUARE = [
    {"lat": 19.0, "lon": 72.85},
    {"lat": 19.01, "lon": 72.85},
    {"lat": 19.01, "lon": 72.86},
    {"lat": 19.0, "lon": 72.86},
]


def _square_geojson(lon_lat_ring):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [lon_lat_ring + [lon_lat_ring[0]]],
                },
                "properties": {},
            }
        ],
    }


def test_ingest_requires_authentication(anon_client):
    """No anonymous caller may push geometry into the platform."""
    for path, kwargs in (
        ("/api/v1/ingest/gnss", {"json": {"points": MUMBAI_SQUARE}}),
        ("/api/v1/ingest/parcel-geojson", {"json": {"geojson": _square_geojson(
            [[72.85, 19.0], [72.86, 19.0], [72.86, 19.01], [72.85, 19.01]])}}),
    ):
        r = anon_client.post(path, **kwargs)
        assert r.status_code in (401, 403), (path, r.status_code, r.text)


def test_gnss_area_is_not_square_degrees(authed_verify):
    """A 0.01 x 0.01 degree box is ~1.1 x 1.0 km, i.e. over 1e6 m^2.

    Multiplying the degree deltas gives 0.0001 -- an answer 10 orders of
    magnitude too small that still looks like a number, which is why the
    assertion is on magnitude rather than on the presence of `area_m2`.
    """
    r = authed_verify.post(
        "/api/v1/ingest/gnss", json={"points": MUMBAI_SQUARE, "description": "survey box"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["point_count"] == 4

    area = body["area_m2"]
    assert area is not None
    # ~1.1 km^2. The square-degrees answer would be 1e-4.
    assert 5e5 < area < 5e6, area

    assert "degrees NOT treated as meters" in body["computation_method"]
    assert body["crs"].startswith("EPSG:4326")


def test_gnss_rejects_points_outside_india(authed_verify):
    """A ring in the Gulf of Guinea is not an Indian survey."""
    r = authed_verify.post(
        "/api/v1/ingest/gnss",
        json={
            "points": [
                {"lat": 0.0, "lon": 0.0},
                {"lat": 0.01, "lon": 0.0},
                {"lat": 0.01, "lon": 0.01},
                {"lat": 0.0, "lon": 0.01},
            ]
        },
    )
    assert r.status_code in (400, 422), (r.status_code, r.text)
    assert "outside" in r.text.lower() or "india" in r.text.lower()


def test_geojson_outside_india_bounds_rejected(authed_verify):
    r = authed_verify.post(
        "/api/v1/ingest/parcel-geojson",
        json={"geojson": _square_geojson([[0, 0], [1, 0], [1, 1], [0, 1]])},
    )
    assert r.status_code == 422, (r.status_code, r.text)
    assert "outside India bounds" in r.json()["detail"]


def test_geojson_inside_india_accepted_and_labelled(authed_verify):
    """Valid geometry succeeds, and a builder-asserted import stays labelled."""
    r = authed_verify.post(
        "/api/v1/ingest/parcel-geojson",
        json={
            "geojson": _square_geojson(
                [[72.85, 19.0], [72.86, 19.0], [72.86, 19.01], [72.85, 19.01]]
            ),
            "is_authoritative": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["valid_count"] == 1
    assert body["rejected_features"] == []

    # area is real geometry, not square degrees
    assert body["area_m2"] is not None and body["area_m2"] > 5e5

    prov = body["provenance"]
    # `is_authoritative: false` was requested, so nothing may claim authority.
    assert prov["is_real"] is False
    assert prov["is_derived"] is True
    assert prov["has_authentic_source"] is False
    assert prov["source"] == "BUILDER_ASSERTED"
    assert prov["confidence_tier"] == "LOW"


def test_point_cloud_result_is_labelled_derived(authed_verify):
    """Point clouds have no authentic source here, so the label must say so."""
    csv = "x,y,z\n0,0,0\n1,0,0\n1,1,0\n0,1,0\n"
    r = authed_verify.post(
        "/api/v1/ingest/point-cloud",
        files={"file": ("probe.csv", io.BytesIO(csv.encode()), "text/csv")},
    )
    # The pipeline may legitimately reject this toy CSV; what must never happen
    # is a 200 that reports derived geometry as authentic.
    if r.status_code == 200:
        prov = r.json()["provenance"]
        assert prov["is_derived"] is True
        assert prov["is_real"] is False
        assert prov["data_type"] == "POINT_CLOUD_DERIVED"
        assert "DERIVED" in prov["provenance"] or "MODELLED" in prov["provenance"]
        # No invented model authority.
        assert "cnn" not in prov["provenance"].lower()
    else:
        # A pipeline that cannot process the upload now reports a server error
        # instead of answering 200 with `result={"error": ...}`. 500 is the
        # honest status for "accepted, then failed"; 4xx stays for input the
        # route can reject up front.
        assert r.status_code in (400, 415, 422, 500), (r.status_code, r.text)
        if r.status_code == 500:
            assert "failed" in r.json()["detail"].lower()


def test_oversized_upload_is_rejected(authed_verify):
    """Size is checked from the stream, so the rejection cannot be a buffering win."""
    oversized = b"x" * (51 * 1024 * 1024)
    r = authed_verify.post(
        "/api/v1/ingest/drone-exif",
        files={"file": ("huge.jpg", io.BytesIO(oversized), "image/jpeg")},
    )
    assert r.status_code == 413, (r.status_code, r.text)
    assert "size limit" in r.json()["detail"].lower()


def test_drone_exif_without_gps_reports_that(authed_verify):
    """A photo with no GPS tag is a real photo with no location in it."""
    # Minimal valid 1x1 PNG, which carries no EXIF and therefore no GPS.
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000d4944415478da63fcffff3f0300050001ff9d1b1e"
        "0000000049454e44ae426082"
    )
    r = authed_verify.post(
        "/api/v1/ingest/drone-exif",
        files={"file": ("probe.png", io.BytesIO(png), "image/png")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_gps"] is False
    assert body["gps"] is None
    # Embedded metadata is what it is: not a georeferenced capture.
    assert body["provenance"]["is_real"] is False
