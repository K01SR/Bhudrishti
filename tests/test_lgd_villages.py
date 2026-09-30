"""LGD village directory: real places, and a hard limit on what they may mean.

The point of these tests is to keep the directory honest. A village from the
Local Government Directory is a real administrative unit, so the app may search,
navigate and attribute it. It is not a property record, so no field may imply a
parcel, an owner, a plot area or a land use, and the module must stay quietly
usable when the SQLite build is absent.
"""
from __future__ import annotations

import os

import pytest

from app.pipelines import lgd_villages

BUILT = lgd_villages.is_available()

requires_build = pytest.mark.skipif(
    not BUILT, reason="lgd_villages.sqlite not built; run scripts/build_lgd_villages.py"
)

# Airoli, Thane district, Maharashtra: the SIH pilot area, real LGD code.
PILOT_VILLAGE_CODE = "943726"


class TestAvailability:
    def test_module_imports_without_database(self):
        assert callable(lgd_villages.search_villages)

    def test_status_reports_build_state(self):
        # Either answer is honest; claiming presence falsely is not.
        assert lgd_villages.is_available() == os.path.exists(
            lgd_villages.database_path()
        )

    def test_missing_database_yields_empty_not_error(self):
        if BUILT:
            pytest.skip("database present, the absence path is not exercised")
        assert lgd_villages.count_villages() == 0
        assert lgd_villages.search_villages("nerul") == []
        assert lgd_villages.list_states() == []
        assert lgd_villages.get_village(PILOT_VILLAGE_CODE) is None


@requires_build
class TestRealRecords:
    def test_pilot_village_is_present_by_official_code(self):
        record = lgd_villages.get_village(PILOT_VILLAGE_CODE)
        assert record is not None
        assert record["village_name"] == "Airoli"
        assert record["state_name"] == "Maharashtra"
        assert record["district_name"] == "Thane"

    def test_unknown_code_is_none(self):
        assert lgd_villages.get_village("000000") is None

    def test_every_row_carries_a_census_join_key(self):
        # The Census 2011 code is the only handle that ties a present-day
        # directory entry to the national census tables, so it may not be blank.
        assert lgd_villages.count_villages() > 600_000
        sample = lgd_villages.list_villages(limit=20000)
        assert sample
        assert all(row["census_2011_code"] for row in sample)

    def test_search_finds_known_places(self):
        hits = lgd_villages.search_villages("nerul", 10)
        assert hits, "expected at least one village named Nerul"
        assert any(hit["village_name"] == "Nerul" for hit in hits)
        assert any(hit["state_name"] == "Maharashtra" for hit in hits)

    def test_search_ranks_exact_name_first(self):
        hits = lgd_villages.search_villages("Airoli", 20)
        assert hits
        assert hits[0]["village_name"].lower().startswith("airoli")

    def test_blank_query_returns_nothing(self):
        assert lgd_villages.search_villages("") == []
        assert lgd_villages.search_villages("   ") == []

    def test_cascade_resolves_state_down_to_villages(self):
        districts = lgd_villages.list_districts("Maharashtra")
        assert any(d["district_name"] == "Thane" for d in districts)

        subdistricts = lgd_villages.list_subdistricts("Maharashtra", "Thane")
        assert subdistricts
        assert all(s["district_name"] == "Thane" for s in subdistricts)

        villages = lgd_villages.villages_in_subdistrict(
            subdistricts[0]["subdistrict_code"]
        )
        assert villages
        assert all(v["district_name"] == "Thane" for v in villages)
        assert all(v["state_name"] == "Maharashtra" for v in villages)

    def test_unknown_state_is_empty(self):
        assert lgd_villages.list_districts("Atlantis") == []


@requires_build
class TestProvenanceAndLimits:
    def test_results_declare_source_and_retrieval_date(self):
        prov = lgd_villages.get_village(PILOT_VILLAGE_CODE)["provenance"]
        assert prov["source"] == "lgd"
        assert prov["authoritative"] is True
        assert prov["publisher"]
        assert prov["source_url"].startswith("https://lgdirectory.gov.in")
        assert prov["retrieved"]

    def test_provenance_states_the_non_cadastre_limit(self):
        prov = lgd_villages.get_village(PILOT_VILLAGE_CODE)["provenance"]
        assert "no parcel boundaries" in prov["note"]

    def test_records_expose_no_geometry(self):
        # LGD rows carry no coordinates, so the loader says so instead of
        # inventing a centroid from the place name.
        assert lgd_villages.get_village(PILOT_VILLAGE_CODE)["geometry_kind"] == "none"

    def test_no_record_implies_property_ownership(self):
        record = lgd_villages.get_village(PILOT_VILLAGE_CODE)
        forbidden = {
            "owner", "owner_name", "ulpin", "plot_area", "area_sqm",
            "land_use", "zoning", "fsi", "survey_number", "title",
        }
        assert not forbidden & set(record)

    def test_manifest_records_vintage_and_checksums(self):
        meta = lgd_villages.manifest()
        assert meta["source_url"].startswith("https://lgdirectory.gov.in")
        assert meta["retrieved_utc"]
        assert meta["total_villages"] > 600_000
        assert meta["rows_by_state"]
        assert all("sha256" in source for source in meta["sources"])
