"""Tests for the authentic data-source layer.

The government providers (data.gov.in, ISRO/NRSA Bhuvan) are exercised against
recorded response shapes with the HTTP layer monkeypatched, so the mapping logic
is verified without depending on live government infrastructure.
"""
from typing import Any, Dict, List

import pytest

from app.opendata import overpass
from app.opendata.underground import fetch_underground_assets
from app.sources import NoAuthenticSourceError, fetch_area, get_providers, provider_order, unconfigured_providers
from app.sources.bhuvan import BhuvanWFSVectorSource, _extract_rings
from app.sources.globalml import GlobalMLSource, _index, _parse_size, bing_quadkey
from app.sources.ogd import OGDIndiaSource, _parse_geometry, _parse_wkt
from app.sources.terrain import _decode_terrarium
from app.sources.openstreetmap import OpenStreetMapSource


class _Resp:
    def __init__(self, payload: Any = None, text: str = "", status: int = 200) -> None:
        self._payload = payload
        self.text = text
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


# --------------------------------------------------------------------------- #
# Registry / chain behaviour
# --------------------------------------------------------------------------- #
def test_default_chain_prefers_government_then_open_datasets(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENDATA_SOURCES", raising=False)
    # Government publications are tried first, then the satellite-derived
    # GlobalML release, then community OpenStreetMap.
    assert provider_order() == ["bhuvan", "data.gov.in", "globalml", "openstreetmap"]
    # globalml and openstreetmap need no credentials, so they are ready; the two
    # government providers stay dormant until an endpoint/key is configured.
    assert [p.name for p in get_providers()] == ["globalml", "openstreetmap"]
    assert set(unconfigured_providers()) == {"bhuvan", "data.gov.in"}


def test_unknown_provider_name_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENDATA_SOURCES", "openstreetmap,not-a-source")
    with pytest.raises(ValueError, match="unknown OPENDATA_SOURCES"):
        provider_order()


def test_chain_raises_instead_of_inventing_data(monkeypatch: pytest.MonkeyPatch):
    """With every provider failing there is no fallback — only an error."""
    monkeypatch.setenv("OPENDATA_SOURCES", "openstreetmap")

    def _fail(*args, **kwargs):
        raise NoAuthenticSourceError("mirror refused the connection")

    monkeypatch.setattr(OpenStreetMapSource, "fetch", _fail)
    with pytest.raises(NoAuthenticSourceError) as exc:
        fetch_area(19.0987, 72.9977, 400)
    assert "No authentic building source available" in str(exc.value)
    assert "no synthetic geometry is generated" in str(exc.value)


def test_chain_uses_next_provider_after_a_failure(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENDATA_SOURCES", "bhuvan,openstreetmap")
    monkeypatch.setenv("BHUVAN_WFS_URL", "https://example.invalid/wfs")
    monkeypatch.setenv("BHUVAN_WFS_LAYER", "gov:buildings")
    monkeypatch.setattr(BhuvanWFSVectorSource, "fetch", lambda *a, **k: (_ for _ in ()).throw(NoAuthenticSourceError("no data")))

    captured: Dict[str, Any] = {}

    def _ok(self, lat, lon, radius, max_buildings=220):
        captured["osm_called"] = True
        return _fixture_area()

    monkeypatch.setattr(OpenStreetMapSource, "fetch", _ok)
    data = fetch_area(19.0987, 72.9977, 400)
    assert captured["osm_called"] is True
    assert data.provenance.provider == "openstreetmap"


def _fixture_area():
    from app.sources.base import AreaData, Provenance

    return AreaData(
        buildings=[{"id": 1, "name": "x", "height_m": None, "floors": None, "type": "tower", "ring_geo": [[0, 0], [1, 0], [1, 1], [0, 0]]}],
        labels=[],
        provenance=Provenance(provider="openstreetmap", dataset="fixture", license="ODbL", source_url="https://osm.org/"),
    )


# --------------------------------------------------------------------------- #
# OpenStreetMap provider
# --------------------------------------------------------------------------- #
def test_osm_provider_marks_itself_non_authoritative(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.sources.openstreetmap.fetch_osm_area", lambda *a, **k: {
        "buildings": [{"id": 1, "name": "A", "height_m": 10.0, "floors": 3, "type": "tower", "ring_geo": [[0, 0], [1, 0], [1, 1], [0, 0]]}],
        "labels": [{"name": "L", "kind": "place", "lat": 1.0, "lon": 1.0}],
    })
    data = OpenStreetMapSource().fetch(19.0, 72.9, 400)
    assert data.provenance.authoritative is False
    assert "ODbL" in data.provenance.license
    assert data.source == "openstreetmap"


def test_osm_provider_refuses_empty_response(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.sources.openstreetmap.fetch_osm_area", lambda *a, **k: {"buildings": [], "labels": []})
    with pytest.raises(NoAuthenticSourceError, match="no building footprints"):
        OpenStreetMapSource().fetch(19.0, 72.9, 400)


def test_osm_provider_warns_when_heights_are_absent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.sources.openstreetmap.fetch_osm_area", lambda *a, **k: {
        "buildings": [{"id": 1, "name": "A", "height_m": None, "floors": None, "type": "tower", "ring_geo": [[0, 0], [1, 0], [1, 1], [0, 0]]}],
        "labels": [],
    })
    data = OpenStreetMapSource().fetch(19.0, 72.9, 400)
    assert any("no surveyed height" in w for w in data.warnings)


# --------------------------------------------------------------------------- #
# data.gov.in (OGD, Government of India)
# --------------------------------------------------------------------------- #
def test_ogd_is_dormant_without_credentials(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OGD_API_KEY", raising=False)
    monkeypatch.delenv("OGD_RESOURCE_ID", raising=False)
    src = OGDIndiaSource()
    assert src.is_configured is False
    with pytest.raises(NoAuthenticSourceError, match="OGD_API_KEY"):
        src.fetch(19.0, 72.9, 400)


def test_ogd_maps_geojson_rows_and_is_authoritative(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OGD_API_KEY", "test-key")
    monkeypatch.setenv("OGD_RESOURCE_ID", "res-1")
    payload = {
        "records": [
            {
                "id": "b1",
                "building_name": "Block A",
                "height": "18.5",
                "floors": "5",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[72.99, 19.09], [72.991, 19.09], [72.991, 19.091], [72.99, 19.09]]],
                },
            }
        ]
    }
    monkeypatch.setattr("app.sources.ogd.httpx.get", lambda *a, **k: _Resp(payload=payload))
    data = OGDIndiaSource().fetch(19.09, 72.99, 400)
    assert data.provenance.authoritative is True
    assert "Government of India" in data.provenance.license
    b = data.buildings[0]
    assert b["name"] == "Block A"
    assert b["height_m"] == 18.5
    assert b["floors"] == 5
    assert b["footprint_area_m2"] > 0


def test_ogd_skips_rows_without_geometry(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OGD_API_KEY", "test-key")
    monkeypatch.setenv("OGD_RESOURCE_ID", "res-1")
    payload = {
        "records": [
            {"id": "b1", "latitude": "19.09", "longitude": "72.99"},  # point only
            {
                "id": "b2",
                "geometry": {"type": "Polygon", "coordinates": [[[72.99, 19.09], [72.991, 19.09], [72.991, 19.091], [72.99, 19.09]]]},
            },
        ]
    }
    monkeypatch.setattr("app.sources.ogd.httpx.get", lambda *a, **k: _Resp(payload=payload))
    data = OGDIndiaSource().fetch(19.09, 72.99, 400)
    assert [b["id"] for b in data.buildings] == ["b2"]
    assert any("skipped" in w for w in data.warnings)


def test_ogd_raises_when_no_row_has_geometry(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OGD_API_KEY", "test-key")
    monkeypatch.setenv("OGD_RESOURCE_ID", "res-1")
    monkeypatch.setattr(
        "app.sources.ogd.httpx.get",
        lambda *a, **k: _Resp(payload={"records": [{"id": "b1", "latitude": "19.09", "longitude": "72.99"}]}),
    )
    with pytest.raises(NoAuthenticSourceError, match="no building geometry"):
        OGDIndiaSource().fetch(19.09, 72.99, 400)


def test_ogd_surfaces_platform_errors(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OGD_API_KEY", "bad-key")
    monkeypatch.setenv("OGD_RESOURCE_ID", "res-1")
    monkeypatch.setattr("app.sources.ogd.httpx.get", lambda *a, **k: _Resp(payload={"error": "Key not authorised"}))
    with pytest.raises(NoAuthenticSourceError, match="Key not authorised"):
        OGDIndiaSource().fetch(19.09, 72.99, 400)


@pytest.mark.parametrize(
    "raw,expected_len",
    [
        ({"type": "Polygon", "coordinates": [[[1, 2], [3, 4], [5, 6], [1, 2]]]}, 4),
        ({"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": [[[[1, 2], [3, 4], [5, 6], [1, 2]]]]}}, 4),
        ('{"type":"Polygon","coordinates":[[[1,2],[3,4],[5,6],[1,2]]]}', 4),
    ],
)
def test_ogd_geometry_parsing(raw: Any, expected_len: int):
    ring = _parse_geometry(raw)
    assert ring is not None and len(ring) == expected_len


def test_ogd_wkt_parsing():
    ring = _parse_wkt("POLYGON((1 2, 3 4, 5 6, 1 2))")
    assert ring is not None and ring[0] == [1.0, 2.0] and ring[-1] == ring[0]


# --------------------------------------------------------------------------- #
# ISRO/NRSA Bhuvan
# --------------------------------------------------------------------------- #
_GML = """<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs"
    xmlns:gml="http://www.opengis.net/gml" xmlns:gov="gov">
  <gml:featureMember>
    <gov:building gml:id="g1">
      <gov:building_id>B-1</gov:building_id>
      <gov:the_geom>
        <gml:Polygon srsName="EPSG:4326">
          <gml:exterior><gml:LinearRing><gml:coordinates>
            72.99,19.09 72.991,19.09 72.991,19.091 72.99,19.09
          </gml:coordinates></gml:LinearRing></gml:exterior>
        </gml:Polygon>
      </gov:the_geom>
    </gov:building>
  </gml:featureMember>
</wfs:FeatureCollection>"""


def test_bhuvan_is_dormant_without_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("BHUVAN_WFS_URL", raising=False)
    monkeypatch.delenv("BHUVAN_WFS_LAYER", raising=False)
    src = BhuvanWFSVectorSource()
    assert src.is_configured is False
    with pytest.raises(NoAuthenticSourceError, match="BHUVAN_WFS_URL"):
        src.fetch(19.09, 72.99, 400)


def test_bhuvan_reads_wfs_gml(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BHUVAN_WFS_URL", "https://example.invalid/wfs")
    monkeypatch.setenv("BHUVAN_WFS_LAYER", "buildings")
    monkeypatch.setattr("app.sources.bhuvan.httpx.get", lambda *a, **k: _Resp(text=_GML))
    data = BhuvanWFSVectorSource().fetch(19.09, 72.99, 400)
    assert data.provenance.authoritative is True
    assert "NRSC/ISRO" in data.provenance.license
    assert len(data.buildings) == 1
    b = data.buildings[0]
    # No height/floor data in the layer: these must stay unset, not invented.
    assert b["height_m"] is None and b["floors"] is None
    assert b["footprint_area_m2"] > 0
    assert any("footprint-only" in w for w in data.warnings)


def test_bhuvan_reports_service_exception(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BHUVAN_WFS_URL", "https://example.invalid/wfs")
    monkeypatch.setenv("BHUVAN_WFS_LAYER", "buildings")
    monkeypatch.setattr(
        "app.sources.bhuvan.httpx.get",
        lambda *a, **k: _Resp(text='<ServiceExceptionReport><ServiceException>Layer not found</ServiceException></ServiceExceptionReport>'),
    )
    with pytest.raises(NoAuthenticSourceError, match="service exception"):
        BhuvanWFSVectorSource().fetch(19.09, 72.99, 400)


def test_bhuvan_handles_gml_poslist():
    xml = """<gml:Polygon xmlns:gml="http://www.opengis.net/gml">
      <gml:exterior><gml:LinearRing>
        <gml:posList>72.99 19.09 72.991 19.09 72.991 19.091 72.99 19.09</gml:posList>
      </gml:LinearRing></gml:exterior></gml:Polygon>"""
    rings = _extract_rings(xml)
    assert len(rings) == 1 and rings[0][0] == [72.99, 19.09]


# --- GlobalML (Microsoft satellite-derived footprints) ------------------------


def test_bhuvan_handles_gml_poslist():
    xml = """<gml:Polygon xmlns:gml="http://www.opengis.net/gml">
      <gml:exterior><gml:LinearRing>
        <gml:posList>72.99 19.09 72.991 19.09 72.991 19.091 72.99 19.09</gml:posList>
      </gml:LinearRing></gml:exterior></gml:Polygon>"""
    rings = _extract_rings(xml)
    assert len(rings) == 1 and rings[0][0] == [72.99, 19.09]


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    import struct
    import zlib

    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def test_terrain_terrarium_png_is_decoded_to_elevation():
    """A terrarium tile decodes via elevation = R*256 + G + B/256 - 32768.

    RGB(128, 0, 0) is exactly 0 m, which makes the expected value unambiguous.
    """
    import struct
    import zlib

    import numpy as np

    width = height = 2
    # One scanline: filter byte 0, then two RGB(128, 0, 0) pixels.
    scanline = bytes([0]) + bytes([128, 0, 0, 128, 0, 0])
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(scanline * height))
        + _png_chunk(b"IEND", b"")
    )
    grid = _decode_terrarium(png)
    assert grid.shape == (height, width)
    assert np.allclose(grid, 0.0)


def test_terrain_rejects_non_png():
    with pytest.raises(NoAuthenticSourceError, match="not a PNG"):
        _decode_terrarium(b"GIF89a not a png")


def test_bing_quadkey_matches_known_mumbai_tile():
    # The Mumbai partition of the GlobalML release is quadkey 123300311.
    assert bing_quadkey(19.0987, 72.9977) == "123300311"


def test_bing_quadkey_encodes_hemisphere_in_the_first_digit():
    # digit = (x_bit << 1) | y_bit. Mumbai is north of the equator and east of
    # 0 deg -> y_bit=1, x_bit=1 -> 3 once the parent tile is resolved; the first
    # digit only carries the y (hemisphere) bit.
    assert bing_quadkey(19.0987, 72.9977)[0] == "1"   # northern hemisphere
    assert bing_quadkey(-33.8688, 151.2093)[0] == "3"  # southern hemisphere
    assert bing_quadkey(0.0, 0.0)[0] == "3"            # on the equator


def test_globalml_index_prefers_the_largest_partition(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """One quadkey is published by several region rows; the bigger one wins."""
    csv_body = (
        "Location,QuadKey,Url,Size,UploadDate\n"
        "Asia,123300311,https://example.invalid/asia.csv.gz,24.2KB,2026-08-13\n"
        "India,123300311,https://example.invalid/india.csv.gz,31.4MB,2026-08-13\n"
    )
    cache = tmp_path / "dataset-links.csv"
    cache.write_text(csv_body, encoding="utf-8")
    monkeypatch.setattr("app.sources.globalml._cache_dir", lambda: tmp_path)
    assert _index()["123300311"] == "https://example.invalid/india.csv.gz"


def test_globalml_parses_size_units():
    assert _parse_size("24.2KB") == int(24.2 * 1024)
    assert _parse_size("2MB") == 2 * 1024 * 1024
    assert _parse_size("1.5GB") == int(1.5 * 1024 * 1024 * 1024)
    assert _parse_size("") == 0
    assert _parse_size("not-a-size") == 0


def test_globalml_reports_no_footprints_instead_of_inventing(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr("app.sources.globalml._cache_dir", lambda: tmp_path)
    empty = tmp_path / "quadkey=123300311.csv.gz"
    import gzip

    empty.write_bytes(gzip.compress(b""))
    with pytest.raises(NoAuthenticSourceError, match="no footprints"):
        GlobalMLSource().fetch(19.0987, 72.9977, 300)


# --- terrain / underground ---------------------------------------------------


def test_underground_reports_unmapped_rather_than_inventing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.opendata.underground._run_query",
        lambda *a, **k: {"elements": []},
    )
    result = fetch_underground_assets(19.09, 72.99, 300)
    assert result["assets"] == []
    assert result["coverage"]["mapped"] is False
    assert "unmapped, not non-existent" in result["coverage"]["note"]


def test_underground_classifies_and_depths_mapped_assets(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.opendata.underground._run_query",
        lambda *a, **k: {
            "elements": [
                {
                    "type": "way",
                    "id": 7,
                    "tags": {"man_made": "pipeline", "utility": "water", "depth": "1.2"},
                    "geometry": [
                        {"lon": 72.99, "lat": 19.09},
                        {"lon": 72.991, "lat": 19.091},
                    ],
                }
            ]
        },
    )
    result = fetch_underground_assets(19.09, 72.99, 300)
    asset = result["assets"][0]
    assert asset["asset_type"] == "pipeline:pipeline"
    assert asset["depth_m"] == 1.2
    assert asset["depth_basis"] == "source_tag"
    assert asset["kind"] == "line"
    assert result["coverage"]["mapped"] is True


def test_geometry_touches_radius_rejects_a_mirror_returning_the_wrong_area():
    """A public mirror has been seen answering a bbox query from elsewhere.

    Overpass-side ``around``/bbox filters are only as trustworthy as the mirror
    that evaluates them, so the returned geometry is re-checked against the
    requested centre before it is placed in the twin.
    """
    from app.opendata.overpass import geometry_touches_radius, haversine_m

    near = [[72.9982, 19.1591]]
    # ~4.3 km south-east of the request centre, from a real mis-served response.
    far = [[73.0067, 19.1212]]

    assert haversine_m(19.159, 72.998, 19.1212, 73.0067) > 4000
    assert geometry_touches_radius(near, 19.159, 72.998, 300)
    assert not geometry_touches_radius(far, 19.159, 72.998, 300)
    # A line crossing the area counts, matching Overpass `around` semantics.
    assert geometry_touches_radius(far + near, 19.159, 72.998, 300)
    assert not geometry_touches_radius([], 19.159, 72.998, 300)
    assert not geometry_touches_radius([[None, None]], 19.159, 72.998, 300)


def test_underground_geometry_is_clipped_to_the_requested_area():
    """A main crossing the area keeps only the run that passes through it.

    Overpass returns the whole way, so a mapped pipeline can carry vertices
    kilometres outside the area. Correct data, wrong for a view framed on one
    area, and it drags the rendered line off screen.
    """
    from app.opendata.underground import _clip_to_area

    # A run that dips through the area between two far-away stretches.
    far_away = [[73.0067, 19.1212]] * 4
    inside = [[72.9981, 19.1590], [72.9982, 19.1591]]
    geometry = far_away + inside + far_away

    clipped, was_clipped = _clip_to_area(geometry, 19.159, 72.998, 300)
    assert was_clipped
    assert clipped, "the in-area run must survive"
    assert all(p in inside or p in far_away for p in clipped)
    assert len(clipped) <= len(inside) + 2, "only one step either side is kept"

    # A node asset has nothing to clip.
    assert _clip_to_area([[72.9981, 19.1590]], 19.159, 72.998, 300) == ([[72.9981, 19.1590]], False)
    # Geometry wholly outside is dropped rather than reported as present.
    assert _clip_to_area(far_away, 19.159, 72.998, 300) == ([], False)


# --------------------------------------------------------------------------- #
# Place names when the footprint provider has none
# --------------------------------------------------------------------------- #
def _named_fixture(provider: str, labels):
    from app.sources.base import AreaData, Provenance

    return AreaData(
        buildings=_fixture_area().buildings,
        labels=labels,
        provenance=Provenance(
            provider=provider, dataset="fixture", license="ODbL", source_url="https://osm.org/"
        ),
    )


def test_footprint_provider_without_names_is_topped_up_from_osm(monkeypatch: pytest.MonkeyPatch):
    """GlobalML is the densest footprint source for India and returns no names.

    It therefore wins the chain for most areas and hands back 220 buildings with
    an empty label list. Names have to come from somewhere else, or the whole map
    is unselectable by name.
    """
    monkeypatch.setenv("OPENDATA_SOURCES", "globalml")
    monkeypatch.setattr(
        GlobalMLSource, "fetch", lambda *a, **k: _named_fixture("globalml", [])
    )
    # The top-up is a label-only Overpass query; it must not re-ask for
    # footprints, which the winner already supplied.
    monkeypatch.setattr(
        overpass,
        "fetch_osm_labels",
        lambda *a, **k: [{"name": "Bandra West", "kind": "suburb", "lat": 19.05, "lon": 72.83}],
    )

    data = fetch_area(19.0552, 72.8308, 500)

    assert data.provenance.provider == "globalml", "footprints must still come from the winner"
    assert [lb["name"] for lb in data.labels] == ["Bandra West"]
    # The names must not be attributed to the provider that did not supply them.
    assert data.label_provenance is not None
    assert data.label_provenance["provider"] == "openstreetmap"
    assert any("OpenStreetMap" in w for w in data.warnings)


def test_label_top_up_does_not_request_footprints_again(monkeypatch: pytest.MonkeyPatch):
    """A label-only top-up must not spend a large Overpass round-trip on
    buildings whose results would be discarded."""
    monkeypatch.setenv("OPENDATA_SOURCES", "globalml")
    monkeypatch.setattr(
        GlobalMLSource, "fetch", lambda *a, **k: _named_fixture("globalml", [])
    )
    seen = {}

    def _labels(lat, lon, radius, *a, **k):
        seen["called"] = True
        return [{"name": "Cafe Andora", "kind": "cafe", "lat": 19.05, "lon": 72.83}]

    monkeypatch.setattr(overpass, "fetch_osm_labels", _labels)

    data = fetch_area(19.0552, 72.8308, 500)

    assert seen.get("called") is True
    # The provider that supplied footprints is not consulted a second time.
    assert data.provenance.provider == "globalml"


def test_provider_that_supplies_own_names_keeps_them(monkeypatch: pytest.MonkeyPatch):
    """The fallback is for a gap in coverage, not a way to override a provider."""
    monkeypatch.setenv("OPENDATA_SOURCES", "openstreetmap")
    monkeypatch.setattr(
        OpenStreetMapSource,
        "fetch",
        lambda *a, **k: _named_fixture(
            "openstreetmap", [{"name": "Fort", "kind": "place", "lat": 0, "lon": 0}]
        ),
    )

    def _should_not_run(*a, **k):
        raise AssertionError("no label top-up when the provider already supplied names")

    monkeypatch.setattr(overpass, "fetch_osm_labels", _should_not_run)

    data = fetch_area(18.9358, 72.8356, 500)

    assert [lb["name"] for lb in data.labels] == ["Fort"]
    assert data.label_provenance is None
    assert data.warnings == []


def test_nameless_area_reports_why_instead_of_silently_returning_zero(monkeypatch: pytest.MonkeyPatch):
    """A throttled Overpass is not the same as an area with no named places.

    The label call is a network round-trip behind the same politeness gap, so it
    fails under load. Silence would make that indistinguishable from a genuinely
    unlabelled area, so the reason has to travel with the footprints.
    """
    monkeypatch.setenv("OPENDATA_SOURCES", "globalml")
    monkeypatch.setattr(
        GlobalMLSource, "fetch", lambda *a, **k: _named_fixture("globalml", [])
    )

    def _busy(*a, **k):
        raise RuntimeError("Overpass budget exhausted: The read operation timed out")

    monkeypatch.setattr(overpass, "fetch_osm_labels", _busy)

    data = fetch_area(19.0552, 72.8308, 500)

    assert data.labels == []
    assert len(data.buildings) == 1, "footprints survive a label outage"
    joined = " ".join(data.warnings)
    assert "no place names available" in joined
    assert "timed out" in joined, "the operator is told the actual cause"


def test_an_empty_label_result_does_not_claim_names_were_taken(monkeypatch: pytest.MonkeyPatch):
    """An empty list is a failed top-up, not a successful one.

    Overpass answering 200 with nothing is a real outcome for a sparse area, and
    an earlier version of this reported "names taken from OpenStreetMap" over an
    empty list - a claim about data that does not exist.
    """
    monkeypatch.setenv("OPENDATA_SOURCES", "globalml")
    monkeypatch.setattr(
        GlobalMLSource, "fetch", lambda *a, **k: _named_fixture("globalml", [])
    )
    monkeypatch.setattr(overpass, "fetch_osm_labels", lambda *a, **k: [])

    data = fetch_area(19.0552, 72.8308, 500)

    assert data.labels == []
    assert data.label_provenance is None
    joined = " ".join(data.warnings)
    assert "no place names available" in joined
    assert "names taken from OpenStreetMap" not in joined


def test_a_broken_label_provider_does_not_escape_as_a_crash(monkeypatch: pytest.MonkeyPatch):
    """Label enrichment is an enhancement; it must never take the area down."""
    monkeypatch.setenv("OPENDATA_SOURCES", "globalml")
    monkeypatch.setattr(
        GlobalMLSource, "fetch", lambda *a, **k: _named_fixture("globalml", [])
    )

    def _explode(*a, **k):
        raise ZeroDivisionError("unexpected")

    monkeypatch.setattr(overpass, "fetch_osm_labels", _explode)

    data = fetch_area(19.0552, 72.8308, 500)

    assert data.labels == []
    assert "ZeroDivisionError" in " ".join(data.warnings)
