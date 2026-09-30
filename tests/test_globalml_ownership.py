"""Guards on what the GlobalML footprint backend and the ownership detector claim.

Two things are pinned here.

The backend is a retrieval adapter for a published dataset, not a network this
repository trained. The prompts that asked for it described a "pre-trained CNN
semantic segmentation" engine, and the honest version of that feature has to say
what it actually does: fetch footprints Microsoft already published, attach that
dataset's provenance, and derive any height while labelling the derivation. So
the tests below assert the negative — that nothing in the reported surface claims
a model, a detection quality or a confidence figure — and the positive, that
every height leaves tagged with where it came from.

The ownership detector is not R010 again. R010 already reports duplicate
spatial claims and R011 duplicate properties; a file that re-derived either would
double-count one defect in every report. The tests below check the division of
labour in both directions: a batch of repeated spatial identities produces no
title finding here and is handed to R010 instead, and a batch of *distinct*
identities overlapping under different parties produces a finding here while R010
has nothing to say about it.
"""
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.pipelines.neural import (
    MODELLED_HEIGHT_BASIS,
    GlobalMLFootprintBackend,
    NeuralBackendUnavailable,
    describe_backends,
    get_active_engine,
    get_footprint_source,
    get_neural_backend,
)
from app.qa_engine.ownership_clash import OwnershipClashDetector
from app.qa_engine.rules import RuleSeverity, RuleStatus, TopologyQAEngine
from app.sources.base import AreaData, Provenance

# Words that would turn a dataset retrieval into a claim about a model. Scanned
# against every string the backend reports, not against its prose: the module is
# allowed to say it runs no model, not allowed to report that it ran one.
MODEL_CLAIM_TOKENS = (
    "cnn",
    "convolutional",
    "unet",
    "pretrained",
    "pre-trained",
    "segmentation",
    "accuracy",
    "confiden",
    "iou",
    "f1-",
    "score",
)
QUALITY_KEY = re.compile(r"(accuracy|confidence|precision|recall|iou|quality_score|f1)", re.IGNORECASE)

GML_PROVENANCE = Provenance(
    provider="globalml",
    dataset="Microsoft GlobalML Building Footprints (test fixture)",
    license="CDLA Permissive 2.0 (Microsoft GlobalML Building Footprints)",
    source_url="https://github.com/microsoft/GlobalMLBuildingFootprints",
    authoritative=False,
)


def _strings(payload):
    """Every string value reachable from a payload, keys excluded."""
    found = []
    if isinstance(payload, dict):
        for value in payload.values():
            found.extend(_strings(value))
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            found.extend(_strings(item))
    elif isinstance(payload, str):
        found.append(payload)
    return found


def _stub_area():
    """AreaData shaped like a real GlobalML answer: no heights, no floor counts.

    The India partitions carry ``height`` of -1 and no floor attribute, which the
    source turns into ``height_m=None`` with ``height_basis="modelled"``. The
    second building here carries a published height so both branches are covered.
    """
    ring_a = [[72.9966, 19.1541], [72.9967, 19.1541], [72.9967, 19.1542], [72.9966, 19.1542], [72.9966, 19.1541]]
    return AreaData(
        buildings=[
            {
                "id": "GML-123300311-1",
                "name": None,
                "height_m": None,
                "floors": None,
                "type": "unknown",
                "ring_geo": ring_a,
                "center_geo": [72.99665, 19.15415],
                "footprint_area_m2": 41.2,
                "height_basis": "modelled",
            },
            {
                "id": "GML-123300311-2",
                "name": None,
                "height_m": 24.0,
                "floors": None,
                "type": "unknown",
                "ring_geo": ring_a,
                "center_geo": [72.99665, 19.15415],
                "footprint_area_m2": 41.2,
                "height_basis": "source",
            },
        ],
        labels=[],
        provenance=GML_PROVENANCE,
        warnings=["GlobalML publishes no height estimates for this region"],
    )


# ---------------------------------------------------------------- GlobalML

def test_backend_declares_itself_a_source_adapter_not_a_model():
    described = GlobalMLFootprintBackend().describe()
    assert described["name"] == "globalml-published-footprints"
    assert described["kind"] == "source-adapter"
    assert described["is_neural_model"] is False
    assert described["trained_here"] is False
    assert described["weights"] is None
    assert described["inference_performed"] is False
    # GlobalML is a real dataset but Microsoft is not an Indian title authority.
    assert described["authority"] == "NOT_AUTHORITATIVE"
    # And it says the things it cannot do, so the description is usable on its own.
    assert any("learned parameters" in line for line in described["does_not_produce"])
    assert any("how good the footprints are" in line for line in described["does_not_produce"])


def test_backend_never_reports_model_authority_or_a_quality_figure():
    """The whole reported surface is scanned; a claim anywhere fails the test."""
    described = GlobalMLFootprintBackend().describe()
    for text in _strings(described):
        lowered = text.lower()
        for token in MODEL_CLAIM_TOKENS:
            assert token not in lowered, f"backend reports {token!r}: {text!r}"
    for key in described:
        assert not QUALITY_KEY.search(key), f"describe() exposes a quality key: {key}"

    areas = _stub_area()
    import app.sources.registry as registry

    original = registry.fetch_area
    registry.fetch_area = lambda *a, **kw: areas
    try:
        result = get_footprint_source("globalml-published-footprints").extract_footprints(
            lat=19.1557, lon=72.9984, radius_m=200
        )
    finally:
        registry.fetch_area = original

    # Excluding the strings the source layer itself supplies: the dataset's own
    # name is allowed to say how the publisher made it. What this module reports
    # about itself is not.
    own = {k: v for k, v in result.items() if k not in {"provenance", "label_provenance", "warnings", "footprints"}}
    for text in _strings(own):
        lowered = text.lower()
        for token in MODEL_CLAIM_TOKENS:
            assert token not in lowered, f"payload reports {token!r}: {text!r}"
    for key in own:
        assert not QUALITY_KEY.search(key), f"payload exposes a quality key: {key}"

    model = result["model"]
    assert model["trained_here"] is False
    assert model["weights_loaded"] is False
    assert model["inference_performed"] is False
    assert model["artifact_path"] is None
    assert model["authority"] == "NONE"
    assert result["engine"] == "globalml-published-footprints"
    assert result["method"] == "retrieval_of_published_footprint_dataset"


def test_footprints_carry_the_dataset_provenance_not_a_model_attribution():
    import app.sources.registry as registry

    area = _stub_area()
    original = registry.fetch_area
    registry.fetch_area = lambda *a, **kw: area
    try:
        result = get_footprint_source("globalml-published-footprints").extract_footprints(
            lat=19.1557, lon=72.9984, radius_m=200
        )
    finally:
        registry.fetch_area = original

    assert result["provenance"] == area.provenance.as_dict()
    assert result["provenance"]["authoritative"] is False
    assert result["provenance"]["provider"] == "globalml"
    for footprint in result["footprints"]:
        assert footprint["footprint_provenance"] == area.provenance.as_dict()
        # Real geometry came through, not a placeholder.
        assert len(footprint["ring_geo"]) >= 4
        assert footprint["id"].startswith("GML-")


def test_every_height_is_labelled_with_its_basis():
    import app.sources.registry as registry

    area = _stub_area()
    original = registry.fetch_area
    registry.fetch_area = lambda *a, **kw: area
    try:
        result = get_footprint_source("globalml-published-footprints").extract_footprints(
            lat=19.1557, lon=72.9984, radius_m=200
        )
    finally:
        registry.fetch_area = original

    derived, published = result["footprints"]
    # No height in the source -> one is derived, and it says so in as many words.
    assert derived["height_basis"] == "derived"
    assert derived["height_basis_detail"] == MODELLED_HEIGHT_BASIS
    assert derived["height_basis_detail"].startswith("derived:")
    assert "not a measured height" in derived["height_basis_detail"]
    assert derived["height_m"] is not None and derived["height_m"] > 0
    assert derived["floors"] >= 1
    assert derived["floors_basis"] == "derived"

    # A height the dataset publishes is passed through, tagged as the source's.
    assert published["height_basis"] == "source"
    assert published["height_m"] == 24.0
    assert "globalml" in published["height_basis_detail"]

    assert result["height_basis"]["source"] == 1
    assert result["height_basis"]["derived"] == 1
    assert result["height_basis"]["derived_basis"] == MODELLED_HEIGHT_BASIS

    # Nothing anywhere carries an untagged height.
    for footprint in result["footprints"]:
        assert footprint["height_basis"] in {"source", "derived"}
        assert footprint["height_basis_detail"]


def test_backend_refuses_without_a_coordinate_and_outside_the_configured_chain(monkeypatch):
    backend = GlobalMLFootprintBackend()
    with pytest.raises(NeuralBackendUnavailable):
        backend.extract_footprints()
    # A chain without globalml is an honest outage, not a reason to guess.
    monkeypatch.setenv("OPENDATA_SOURCES", "openstreetmap")
    assert backend.available() is False
    with pytest.raises(NeuralBackendUnavailable):
        backend.extract_footprints(lat=19.1557, lon=72.9984)
    monkeypatch.setenv("OPENDATA_SOURCES", "globalml,openstreetmap")
    assert backend.available() is True


def test_neural_accessors_do_not_report_the_retrieval_adapter_as_a_model():
    adapter = "globalml-published-footprints"
    # get_neural_backend() hands back only backends that run learned parameters.
    # In a default deployment no such backend is configured, so it must be None.
    if get_neural_backend() is None:
        assert get_neural_backend(adapter) is None
    # ...and the adapter is still reachable, through the source accessor.
    assert isinstance(get_footprint_source(adapter), GlobalMLFootprintBackend)
    described = {b["name"]: b for b in describe_backends()}
    assert described[adapter]["is_neural_model"] is False


def test_active_engine_names_the_source_never_a_neural_hook():
    engine = get_active_engine()
    assert engine["trained_model_in_repo"] is False
    assert engine["footprint_refinement"] in {
        "deterministic-lidar",
        "globalml-published-footprints",
        "torch-unet-footprint",
    }
    if get_neural_backend() is None:
        # The bug this guards: a lookup that answers is not a hook that ran.
        assert engine["footprint_refinement"] != "neural-hook"
        assert engine["footprint_refinement"] == "globalml-published-footprints"


def test_backend_reads_the_real_published_dataset_when_the_tile_is_cached():
    """End-to-end against the published tile, no network and no stubbed source.

    Skipped when the cache is absent or stale rather than downloading 20 MB in a
    unit test: an unreachable dataset is an outage to report, not a fixture.
    """
    from app.sources.globalml import _cache_dir, _now, _TILE_TTL_S

    tile = _cache_dir() / "quadkey=123300311.csv.gz"
    if not tile.exists() or (_now() - tile.stat().st_mtime) > _TILE_TTL_S:
        pytest.skip("cached GlobalML tile missing or stale")

    result = get_footprint_source("globalml-published-footprints").extract_footprints(
        lat=19.1557, lon=72.9984, radius_m=150, max_buildings=5
    )
    assert result["footprints_count"] > 0
    assert result["provenance"]["provider"] == "globalml"
    assert result["provenance"]["authoritative"] is False
    assert result["provenance"]["license"].startswith("CDLA Permissive 2.0")
    for footprint in result["footprints"]:
        assert len(footprint["ring_geo"]) >= 4
        assert footprint["height_basis"] in {"source", "derived"}
    # These partitions publish no heights at all, so every one is derived here.
    assert result["height_basis"]["source"] == 0
    assert result["height_basis"]["derived"] == result["footprints_count"]


# ---------------------------------------------------------------- ownership

RING_A = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]
RING_B = [[5.0, 5.0], [15.0, 5.0], [15.0, 15.0], [5.0, 15.0], [5.0, 5.0]]
RING_FAR = [[100.0, 100.0], [110.0, 100.0], [110.0, 110.0], [100.0, 110.0], [100.0, 100.0]]


def _unit(number, ring, rights, status="APPROVED", level="L01", min_z=0.0, max_z=3.0, key=None):
    return {
        "unit_number": number,
        "level_code": level,
        "proposed_3d_id": key or f"PROTO-{level}-{number}",
        "unit_type": "U",
        "min_z": min_z,
        "max_z": max_z,
        "coords": ring,
        # Both plan representations the codebase carries, so the same fixture can
        # be handed to the detector and to TopologyQAEngine.
        "footprint_geojson": {"type": "Polygon", "coordinates": [ring]},
        "status": status,
        "rights": rights,
    }


def _own(party, share=100.0, status="ACTIVE", valid_to=None, right_type="OWNERSHIP"):
    right = {"right_type": right_type, "party_name": party, "share_pct": share, "encumbrance_status": status}
    if valid_to is not None:
        right["valid_to"] = valid_to
    return right


def _finding(report, rule_id):
    return next(f for f in report["findings"] if f["rule_id"] == rule_id)


def test_findings_use_the_existing_engine_shape_and_vocabulary():
    units = [_unit("101", RING_A, [_own("A"), _own("B", 60.0)]), _unit("102", RING_B, [_own("C")])]
    report = OwnershipClashDetector().run_rules(units, parcel_data={"ulpin": "12345678901234"})

    assert report["total_rules"] == 4
    for key in ("total_rules", "passed_rules", "failed_rules", "warning_rules", "overall_status", "findings"):
        assert key in report
    for finding in report["findings"]:
        # The keys app.qa_engine.rules writes, plus the evidence list R009 also
        # carries in its own extra key. One renderer reads all of them.
        assert {"rule_id", "rule_name", "severity", "status", "message", "recommended_action"} <= set(finding)
        assert set(finding) - {"rule_id", "rule_name", "severity", "status", "message", "recommended_action"} == {"details"}
        assert finding["status"] in {RuleStatus.PASS, RuleStatus.FAIL, RuleStatus.WARNING}
        assert finding["severity"] in {
            RuleSeverity.CRITICAL,
            RuleSeverity.HIGH,
            RuleSeverity.MEDIUM,
            RuleSeverity.LOW,
        }
        assert finding["message"]


def test_over_allocated_title_fails_r013():
    units = [_unit("101", RING_A, [_own("Asha Rao", 60.0), _own("Vikram Rao", 60.0)])]
    report = OwnershipClashDetector().run_rules(units)
    finding = _finding(report, "R013")
    assert finding["status"] == RuleStatus.FAIL
    assert finding["severity"] == RuleSeverity.CRITICAL
    conflict = finding["details"][0]
    assert conflict["conflict_type"] == "OVER_ALLOCATED_TITLE"
    assert conflict["recorded_total_share_pct"] == 120.0
    assert {c["party"] for c in conflict["claimants"]} == {"Asha Rao", "Vikram Rao"}
    assert "adjudication" in finding["recommended_action"].lower()


def test_undivided_shares_that_add_up_are_not_reported_as_a_conflict():
    """Co-ownership is ordinary. Calling it a clash is an accusation, not a check."""
    units = [_unit("201", RING_A, [_own("Asha Rao", 50.0), _own("Vikram Rao", 50.0)])]
    report = OwnershipClashDetector().run_rules(units)
    assert _finding(report, "R013")["status"] == RuleStatus.PASS
    assert report["overall_status"] == "PASS"


def test_released_and_expired_rights_are_not_treated_as_live_claims():
    past = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    units = [
        _unit(
            "101",
            RING_A,
            [_own("Asha Rao", 60.0), _own("Former Holder", 60.0, status="RELEASED"), _own("Lapsed Buyer", 60.0, valid_to=past)],
        )
    ]
    report = OwnershipClashDetector().run_rules(units)
    assert _finding(report, "R013")["status"] == RuleStatus.PASS


def test_instrument_claiming_the_same_succession_is_a_contested_claim():
    units = [
        _unit(
            "301",
            RING_A,
            [
                _own("Asha Rao"),
                {"right_type": "WILL", "party_name": "Deceased Holder Estate", "encumbrance_status": "ACTIVE"},
            ],
        )
    ]
    report = OwnershipClashDetector().run_rules(units)
    finding = _finding(report, "R013")
    assert finding["status"] == RuleStatus.FAIL
    assert finding["details"][0]["conflict_type"] == "CONTESTED_SUCCESSIVE_INTEREST"
    assert finding["details"][0]["live_owners"] == ["Asha Rao"]


def test_overlapping_distinct_units_under_different_parties_fail_r014():
    units = [_unit("101", RING_A, [_own("Asha Rao")]), _unit("102", RING_B, [_own("Nikhil Menon")])]
    report = OwnershipClashDetector().run_rules(units)
    finding = _finding(report, "R014")
    assert finding["status"] == RuleStatus.FAIL
    detail = finding["details"][0]
    assert detail["unit_a_key"] != detail["unit_b_key"]
    assert detail["holders_a"] == ["Asha Rao"]
    assert detail["holders_b"] == ["Nikhil Menon"]
    assert 0.0 < detail["overlap_ratio"] < 1.0
    assert detail["overlap_height_m"] == 3.0
    # No area in square metres: the plan frame is the caller's, not ours.
    assert not any(key.endswith("_m2") for key in detail)


def test_detector_does_not_reimplement_r010_duplicate_spatial_claims():
    """R010's case: one space, two records. It must produce no title finding here.

    Two records for Flat 201, each holding a different party's ownership right,
    with footprints laid over each other. Every axis a title check would use here
    looks like a conflict — two holders, shared space — and none of it is a title
    defect: it is one space claimed twice, which is R010's finding to make.
    """
    detector = OwnershipClashDetector()
    units = [
        _unit("201", RING_A, [_own("Asha Rao")], key="PROTO-L01-201"),
        _unit("201", RING_B, [_own("Nikhil Menon")], key="PROTO-L01-201"),
    ]
    # The R010 predicate does fire on this batch ...
    assert detector.shared_spatial_identities(units) == ["PROTO-L01-201"]

    report = detector.run_rules(units)
    # ... and the batch is handed over rather than reported a second time.
    assert report["deferred_to_duplicate_claim"] == ["PROTO-L01-201"]
    assert _finding(report, "R013")["status"] == RuleStatus.PASS
    assert _finding(report, "R014")["status"] == RuleStatus.PASS
    assert _finding(report, "R015")["status"] == RuleStatus.PASS
    assert report["overall_status"] == "PASS"
    # And it never speaks for the rules it is not.
    assert not {f["rule_id"] for f in report["findings"]} & {"R010", "R011", "R012"}


def test_r014_fires_with_no_duplicate_identity_for_r010_to_find():
    """The other direction: distinct identities, so R010 has nothing at all here."""
    detector = OwnershipClashDetector()
    units = [_unit("101", RING_A, [_own("Asha Rao")]), _unit("102", RING_B, [_own("Nikhil Menon")])]
    assert detector.shared_spatial_identities(units) == []
    report = detector.run_rules(units)
    assert report["deferred_to_duplicate_claim"] == []
    assert _finding(report, "R014")["status"] == RuleStatus.FAIL


def test_overlap_under_one_party_is_left_to_the_partition_rule():
    """R004 already reports two of one party's units overlapping; R014 must not."""
    units = [_unit("101", RING_A, [_own("Asha Rao")]), _unit("102", RING_B, [_own("Asha Rao")])]
    report = OwnershipClashDetector().run_rules(units)
    finding = _finding(report, "R014")
    assert finding["status"] == RuleStatus.PASS
    assert "one common party" in finding["message"]

    # The same pair against the engine that owns partition questions: R004 fails.
    engine = TopologyQAEngine()
    res = engine.run_all_rules(
        parcel_data={"polygon_geojson": {"type": "Polygon", "coordinates": [RING_FAR]},
                     "document_area_m2": 100.0, "calculated_area_m2": 100.0},
        structure_data={"footprint_geojson": {"type": "Polygon", "coordinates": [RING_FAR]}},
        levels_data=[],
        units_data=[{k: v for k, v in u.items() if k != "rights"} for u in units],
    )
    assert _finding(res, "R004")["status"] == RuleStatus.FAIL
    assert _finding(res, "R004")["severity"] == RuleSeverity.HIGH


def test_registered_unit_with_no_right_is_a_gap_not_an_accusation():
    units = [_unit("101", RING_A, []), _unit("102", RING_FAR, [_own("Asha Rao")])]
    report = OwnershipClashDetector().run_rules(units)
    finding = _finding(report, "R015")
    assert finding["status"] == RuleStatus.WARNING
    assert finding["severity"] == RuleSeverity.MEDIUM
    assert "L01-101" in finding["details"]
    assert "gap in this register" in finding["message"]
    assert "not evidence that nobody holds title" in finding["message"]


def test_draft_unit_is_not_reported_as_untitled():
    units = [_unit("101", RING_A, [], status="DRAFT"), _unit("102", RING_FAR, [_own("Asha Rao")])]
    report = OwnershipClashDetector().run_rules(units)
    assert _finding(report, "R015")["status"] == RuleStatus.PASS


def test_approved_unit_on_disputed_or_expired_title_warns_r016():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    units = [
        _unit("101", RING_A, [_own("Asha Rao", status="DISPUTED")]),
        _unit("102", RING_FAR, [_own("Vikram Rao", valid_to=past)]),
    ]
    report = OwnershipClashDetector().run_rules(units)
    finding = _finding(report, "R016")
    assert finding["status"] == RuleStatus.WARNING
    units_flagged = {detail["unit"] for detail in finding["details"]}
    assert units_flagged == {"L01-101", "L01-102"}
    assert finding["details"][0]["disputed"]


def test_empty_register_is_not_a_clean_result():
    report = OwnershipClashDetector().run_rules([])
    assert report["register_populated"] is False
    assert report["overall_status"] == "NO_RECORDS"
    for finding in report["findings"]:
        assert finding["status"] == RuleStatus.WARNING
        assert "did not run" in finding["message"]


def test_report_refuses_to_determine_legal_title():
    units = [_unit("101", RING_A, [_own("Asha Rao", 60.0), _own("Vikram Rao", 60.0)])]
    report = OwnershipClashDetector().run_rules(units)
    assert report["authoritative"] is False
    assert report["evidence_basis"] == "RECORD_COMPARISON"
    assert "not a determination of legal title" in report["disclaimer"]
    banned = ("fraud", "forged", "invalid title", "unauthorised", "unauthorized", "illegal", "court")
    for finding in report["findings"]:
        lowered = finding["message"].lower()
        for word in banned:
            assert word not in lowered, f"finding asserts {word!r}: {finding['message']}"


def test_attach_to_merges_into_a_topology_engine_report():
    """Drops into the existing report without the caller reading two shapes."""
    units = [_unit("101", RING_A, [_own("Asha Rao", 60.0), _own("Vikram Rao", 60.0)])]
    engine_report = {
        "total_rules": 12,
        "passed_rules": 12,
        "failed_rules": 0,
        "warning_rules": 0,
        "overall_status": "PASS",
        "findings": [{"rule_id": f"R{i:03d}", "rule_name": "x", "severity": "LOW",
                      "status": RuleStatus.PASS, "message": "m", "recommended_action": None}
                     for i in range(1, 13)],
    }
    merged = OwnershipClashDetector().attach_to(engine_report, units)

    assert merged["total_rules"] == 16
    assert merged["failed_rules"] == 1
    assert merged["overall_status"] == "FAIL"
    assert {f["rule_id"] for f in merged["findings"]} >= {"R010", "R013", "R014", "R015", "R016"}
    # Counters are recomputed over the merged set, so they stay totals.
    assert merged["passed_rules"] + merged["failed_rules"] + merged["warning_rules"] == merged["total_rules"]
    assert merged["ownership_report"]["failed_rules"] == 1
    # The caller's own report is untouched.
    assert engine_report["total_rules"] == 12
    assert len(engine_report["findings"]) == 12