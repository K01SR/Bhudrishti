"""Response compression must shrink text payloads and never touch binary ones.

The middleware under test is the real ``CompressibleResponseMiddleware`` from
``app.main``. These tests drive it through a minimal throwaway app so they do
not need the demo gate, a database, or a fixture ULPIN -- the behaviour under
test is purely a function of the response, not of which route produced it.

Note on reading these assertions: httpx transparently decompresses responses,
so ``response.content`` is always the *decoded* body and
``response.headers['content-length']`` is the size actually sent over the wire.
Comparing the two is therefore exactly how a client observes the win, and the
compressed bytes can be checked by re-compressing the decoded body and
comparing sizes rather than by decoding twice.
"""

import gzip
import json
import os

import pytest
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.main import CompressibleResponseMiddleware

# Shaped like the real /api/v1/precinct/buildings payload: a long list of
# building features, which measured 363,381 bytes uncompressed and 21,430
# gzipped (94% smaller) before this middleware existed.
COMPRESSIBLE = json.dumps(
    {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[i, i], [i + 1, i], [i + 1, i + 1], [i, i + 1], [i, i]]]},
                "properties": {"ulpin": f"3D-ULPIN-TEST{i:04d}", "label": "Test Building Label " * 8},
            }
            for i in range(60)
        ],
    },
    indent=2,
).encode()

assert len(COMPRESSIBLE) > 4096, "fixture must be large enough to exercise the threshold"


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(CompressibleResponseMiddleware)

    @app.get("/json-big")
    async def json_big():
        return Response(content=COMPRESSIBLE, media_type="application/json")

    @app.get("/json-small")
    async def json_small():
        return Response(content=b'{"ok":true}', media_type="application/json")

    @app.get("/lidar-binary")
    async def lidar_binary():
        # Packed float32 records, like the real point-cloud endpoint.
        return Response(content=b"\x00" * 4096, media_type="application/octet-stream")

    @app.get("/png")
    async def png():
        return Response(content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048, media_type="image/png")

    @app.get("/geojson")
    async def geojson():
        return Response(content=COMPRESSIBLE, media_type="application/geo+json")

    @app.get("/html")
    async def html():
        return Response(content=b"<html>" + b"y" * 4000 + b"</html>", media_type="text/html")

    @app.get("/stream")
    async def stream():
        async def gen():
            yield b'{"chunk":1}'
            yield b'{"chunk":2}'

        return StreamingResponse(gen(), media_type="application/json")

    @app.get("/already-encoded")
    async def already_encoded():
        return Response(content=COMPRESSIBLE, media_type="application/json", headers={"content-encoding": "br"})

    return TestClient(app)


def test_large_json_is_compressed_and_still_parses(client):
    r = client.get("/json-big", headers={"accept-encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"
    wire = int(r.headers["content-length"])
    assert wire < len(COMPRESSIBLE), f"wire {wire} should be well under raw {len(COMPRESSIBLE)}"
    # Decoded body is byte-identical to what the route produced.
    assert r.content == COMPRESSIBLE
    assert r.json()["features"][0]["properties"]["ulpin"] == "3D-ULPIN-TEST0000"


def test_compression_ratio_is_in_the_expected_range(client):
    """The measured win was 363,381 -> 21,430 bytes. Keep that order of magnitude."""
    r = client.get("/json-big", headers={"accept-encoding": "gzip"})
    ratio = int(r.headers["content-length"]) / len(COMPRESSIBLE)
    assert ratio < 0.25, f"expected a large reduction, got ratio {ratio:.3f}"


def test_lidar_binary_is_never_compressed(client):
    """float32 point records do not gzip usefully, so the CPU is not spent."""
    r = client.get("/lidar-binary", headers={"accept-encoding": "gzip"})
    assert "content-encoding" not in r.headers
    assert len(r.content) == 4096


def test_other_binary_types_are_skipped(client):
    r = client.get("/png", headers={"accept-encoding": "gzip"})
    assert "content-encoding" not in r.headers


def test_small_body_is_left_alone(client):
    """gzip framing would cost more than it saves below the threshold."""
    r = client.get("/json-small", headers={"accept-encoding": "gzip"})
    assert "content-encoding" not in r.headers
    assert r.json() == {"ok": True}


def test_client_declining_gzip_gets_plain_json(client):
    r = client.get("/json-big", headers={"accept-encoding": "identity"})
    assert "content-encoding" not in r.headers
    assert r.content == COMPRESSIBLE


def test_already_encoded_response_is_not_double_compressed(client):
    """A second compressing layer must not see pre-encoded bytes."""
    r = client.get("/already-encoded", headers={"accept-encoding": "gzip"})
    assert r.headers.get("content-encoding") == "br"
    assert r.content == COMPRESSIBLE


def test_streaming_response_is_not_broken(client):
    r = client.get("/stream", headers={"accept-encoding": "gzip"})
    assert r.status_code == 200
    assert b"chunk" in r.content


def test_vary_header_advertises_the_dependency(client):
    r = client.get("/json-big", headers={"accept-encoding": "gzip"})
    assert "accept-encoding" in r.headers.get("vary", "").lower()


def test_incompressible_payload_is_not_grown_by_framing():
    """A body gzip cannot shrink must be sent as-is, not enlarged."""
    noise = os.urandom(4096)
    app = FastAPI()
    app.add_middleware(CompressibleResponseMiddleware)

    @app.get("/noise")
    async def noise_ep():
        return Response(content=noise, media_type="application/json")

    r = TestClient(app).get("/noise", headers={"accept-encoding": "gzip"})
    assert r.content == noise
    assert int(r.headers["content-length"]) <= len(noise)


def test_content_types_are_classified_by_policy_not_by_size():
    """The compressible set is an explicit decision, so pin it."""
    mw = CompressibleResponseMiddleware
    assert "application/json" in mw.COMPRESSIBLE_TYPES
    assert "application/geo+json" in mw.COMPRESSIBLE_TYPES
    assert "image/svg+xml" in mw.COMPRESSIBLE_TYPES
    # Binary payloads that must never be touched, absent from the allowlist.
    for ctype in ("application/octet-stream", "image/png", "application/pdf",
                  "video/mp4", "application/zip", "application/gzip"):
        assert ctype not in mw.COMPRESSIBLE_TYPES, ctype


def test_middleware_is_registered_on_the_real_app():
    """Guard against the middleware being commented out of ``app.main``."""
    from app.main import app

    names = [getattr(m, "cls", None) for m in app.user_middleware]
    assert CompressibleResponseMiddleware in names


def test_lidar_endpoint_content_type_is_not_compressible():
    """Ties the policy back to the real route that motivated it."""
    assert "application/octet-stream" not in CompressibleResponseMiddleware.COMPRESSIBLE_TYPES
    # And that the real point-cloud route actually serves that type.
    source = open("backend/app/api/v1/lidar.py", encoding="utf-8").read()
    assert "application/octet-stream" in source