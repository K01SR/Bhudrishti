"""Geocoding real LGD place names, and the real tier of global search.

Two things are being defended here.

First, that a place on the map is a real place. The LGD directory names 677,673
villages and publishes no coordinates, so the position comes from Nominatim and
has to be qualified: a geocoded centroid is derived from a community-mapped
feature, and it may be a settlement, or merely something that shares the name. A
test that only asserted "found a lat/lon" would pass for a railway station
called Nerul, which is a different claim from "found Nerul".

Second, that search says so. Global search mixes real LGD villages with
generated PostGIS boundaries and pilot assets, and a caller that cannot tell them
apart will present generated rows as real ones. So the real tier is checked for
its official code and its non-cadastre flag, and the page is checked for the
mixed-provenance marker.

The network is stubbed throughout. These tests assert the query we would send
and how we read the answer, not what Nominatim happens to return today.
"""
from __future__ import annotations

import pytest

from app.sources import nominatim

SETTLEMENT_HIT = {
    "lat": "19.158272",
    "lon": "72.996709",
    "display_name": "Airoli, Navi Mumbai, Thane, Maharashtra, 400708, India",
    "class": "place",
    "type": "suburb",
    "osm_id": 12345,
    "importance": 0.147,
}
STATION_HIT = {
    "lat": "19.033594",
    "lon": "73.018164",
    "display_name": "Nerul, Nerul Village, Navi Mumbai, Thane, Maharashtra, India",
    "class": "railway",
    "type": "station",
    "osm_id": 999,
    "importance": 0.368,
}


@pytest.fixture(autouse=True)
def _no_shared_cache(tmp_path, monkeypatch):
    """Give every test its own cache and let it inspect queries sent."""
    monkeypatch.setattr(nominatim, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(nominatim, "_throttle", lambda: None)
    return tmp_path


def _record(monkeypatch, responses: dict):
    sent: list[str] = []

    def fake_get(url):
        import urllib.parse

        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0]
        sent.append(query)
        for needle, hits in responses.items():
            if needle in query:
                return hits
        return []

    monkeypatch.setattr(nominatim, "_get_json", fake_get)
    return sent


class TestCleanPlace:
    def test_strips_census_suffixes(self):
        assert nominatim.clean_place("Nerul (Ct)") == "Nerul"
        assert nominatim.clean_place("Nerul (Ct.)") == "Nerul"
        assert nominatim.clean_place("Bhilwada (Maha)") == "Bhilwada"

    def test_strips_punctuation_and_collapses_space(self):
        assert nominatim.clean_place("  Ratan-  Lal ") == "Ratan Lal"

    def test_handles_none_and_empty(self):
        assert nominatim.clean_place(None) == ""
        assert nominatim.clean_place("") == ""

    def test_preserves_devanagari(self):
        # Local-language names must survive; the gazetteer indexes them.
        assert nominatim.clean_place("आबीतखिंड") == "आबीतखिंड"


class TestHitRanking:
    def test_settlement_outranks_incidental_feature(self):
        # Nominatim scores the station higher, but "suburb" is the place and
        # "station" is a thing inside it.
        assert nominatim._rank_hit(SETTLEMENT_HIT) < nominatim._rank_hit(STATION_HIT)

    def test_village_beats_suburb_within_place_class(self):
        village = {**SETTLEMENT_HIT, "type": "village"}
        assert nominatim._rank_hit(village) < nominatim._rank_hit(SETTLEMENT_HIT)

    def test_result_declares_its_match_quality(self):
        result = nominatim._hit_to_result(SETTLEMENT_HIT, "q", "village+district+state")
        assert result["is_settlement"] is True
        assert result["match_quality"] == "settlement"

        result = nominatim._hit_to_result(STATION_HIT, "q", "village-only")
        assert result["is_settlement"] is False
        assert result["match_quality"] == "incidental"


class TestGeocodePlace:
    def test_uses_full_context_first(self, monkeypatch):
        sent = _record(monkeypatch, {"Maharashtra": [SETTLEMENT_HIT]})
        result = nominatim.geocode_place("Airoli", "Thane", "Airoli", "Maharashtra")
        assert result["found"] is True
        assert sent[0] == "Airoli, Airoli, Thane, Maharashtra, India"
        assert result["strategy"] == "village+subdistrict+district+state"
        assert result["lat"] == pytest.approx(19.158272)

    def test_omits_absent_subdistrict_from_the_query(self, monkeypatch):
        sent = _record(monkeypatch, {"Maharashtra": [SETTLEMENT_HIT]})
        nominatim.geocode_place("Airoli", "Thane", None, "Maharashtra")
        assert sent[0] == "Airoli, Thane, Maharashtra, India"
        assert "Thane, Thane" not in sent[0]

    def test_relaxes_until_something_matches(self, monkeypatch):
        # The specific query returns nothing, so the code must widen rather
        # than give up. Match only the most generic forms to prove the walk-down.
        sent: list[str] = []

        def fake_get(url):
            import urllib.parse

            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0]
            sent.append(query)
            # Only the bare-village attempts answer.
            return [SETTLEMENT_HIT] if query in ("Abitkhind, India", "Abitkhind") else []

        monkeypatch.setattr(nominatim, "_get_json", fake_get)
        result = nominatim.geocode_place("Abitkhind", "Ahilyanagar", "Akole", "Maharashtra")
        assert result["found"] is True
        assert len(sent) > 1, "expected the query to be relaxed at least once"

    def test_unresolved_is_reported_not_guessed(self, monkeypatch):
        _record(monkeypatch, {})
        result = nominatim.geocode_place("Nowhereville", "Nowhere", None, "Nowhere")
        assert result["found"] is False
        assert "lat" not in result and "lon" not in result
        assert result["strategy"] == "unresolved"
        assert "unresolved rather than guessed" in result["note"]

    def test_blank_name_short_circuits(self, monkeypatch):
        sent = _record(monkeypatch, {"x": [SETTLEMENT_HIT]})
        result = nominatim.geocode_place("   ", "Thane", None, "Maharashtra")
        assert result["found"] is False
        assert sent == []

    def test_answer_is_cached(self, monkeypatch):
        sent = _record(monkeypatch, {"Maharashtra": [SETTLEMENT_HIT]})
        first = nominatim.geocode_place("Airoli", "Thane", None, "Maharashtra")
        before = len(sent)
        second = nominatim.geocode_place("Airoli", "Thane", None, "Maharashtra")
        assert len(sent) == before, "second call must be served from cache"
        assert second["lat"] == first["lat"]

    def test_provenance_is_derived_not_authoritative(self, monkeypatch):
        _record(monkeypatch, {"Maharashtra": [SETTLEMENT_HIT]})
        prov = nominatim.geocode_place("Airoli", "Thane", None, "Maharashtra")["provenance"]
        assert prov["provider"] == "nominatim"
        # OSM is community-mapped and a centroid is a derivation on top of it.
        assert prov["authoritative"] is False
        assert "OpenStreetMap" in prov["license"]


@pytest.fixture
def lgd_dir():
    from app.pipelines import lgd_villages

    if not lgd_villages.is_available():
        pytest.skip("LGD database not built")
    return lgd_villages


class TestRealSearchTier:
    def test_search_returns_real_lgd_villages(self, lgd_dir):
        from app.api.v1 import search as search_module

        result = asyncio_run(search_module.search(q="Airoli", limit=25))
        villages = [r for r in result["results"] if r["kind"] == "village"]
        assert villages, "expected the real LGD tier to return Airoli"

        top = villages[0]
        assert top["source"] == "lgd"
        assert top["village_code"] == "943726"
        assert top["state_name"] == "Maharashtra"
        assert top["district_name"] == "Thane"

    def test_real_results_are_not_presented_as_property_records(self, lgd_dir):
        from app.api.v1 import search as search_module

        result = asyncio_run(search_module.search(q="Airoli", limit=25))
        for row in result["results"]:
            if row["kind"] == "village":
                assert row["is_cadastre"] is False
                # A village has no geometry yet, so the page must not claim a focus.
                assert row["has_focus"] is False
                assert row["focus"] is None
                assert row["locate_url"].endswith("/locate")

    def test_payload_declares_mixed_provenance(self, lgd_dir):
        from app.api.v1 import search as search_module

        result = asyncio_run(search_module.search(q="Thane", limit=25))
        assert result["is_mixed_provenance"] is True
        assert "lgd" in result["real_sources"]

    def test_village_codes_are_searchable(self, lgd_dir):
        from app.api.v1 import search as search_module

        # The LGD row itself is the best available label, so a code is a name.
        result = asyncio_run(search_module.search(q="943726", limit=25))
        assert any(
            r.get("village_code") == "943726" for r in result["results"]
        ), "searching an official LGD code should find that village"


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
