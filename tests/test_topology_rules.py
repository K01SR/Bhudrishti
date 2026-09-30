import pytest
from app.pipelines.synthetic_generator import generate_synthetic_airoli_dataset
from app.qa_engine.rules import TopologyQAEngine, RuleStatus
from app.qa_engine.underground_clash import UndergroundClashDetector
from app.qa_engine.fsi_engine import FSIEngine


def test_topology_qa_engine_runs_its_whole_16_rule_catalogue():
    """One run, one catalogue: R001-R012 spatial plus R013-R016 title.

    The count was 12 and the test asserted 12, which is what let R013-R016 ship
    unwired for as long as they did -- nothing here could notice a rule the engine
    never ran. It now asserts the catalogue's real size and that every id in it
    is present exactly once, so a rule that is dropped or double-reported fails
    instead of quietly changing a number nobody reads.
    """
    dataset = generate_synthetic_airoli_dataset()
    engine = TopologyQAEngine()

    res = engine.run_all_rules(
        parcel_data=dataset["hero_parcel"],
        structure_data=dataset["hero_structure"],
        levels_data=dataset["levels"],
        units_data=dataset["units"],
        subsurface_objects=dataset["subsurface_objects"],
    )

    assert res["total_rules"] == 16
    rule_ids = [f["rule_id"] for f in res["findings"]]
    assert sorted(rule_ids) == [f"R{n:03d}" for n in range(1, 17)]
    assert len(set(rule_ids)) == len(rule_ids), "a rule is reported twice in one run"
    assert res["passed_rules"] + res["failed_rules"] + res["warning_rules"] == 16

    # The deliberate PIPE-DRAIN-01 clash is present but documented as mitigated
    # (encased in a concrete protective sleeve) → the rule resolves PASS. This is
    # what the test is really about: a clash that is detected, recognised as
    # mitigated, and therefore not counted as a failure.
    assert res["failed_rules"] == 0
    r009 = next(f for f in res["findings"] if f["rule_id"] == "R009")
    assert r009["status"] == RuleStatus.PASS
    assert r009["mitigated"] is True
    assert "CRITICAL 3D SUBSURFACE CLASH" in r009["message"]
    assert "MITIGATED" in r009["message"]

    # R013-R016 now run against the same unit rows. R015 warns here, and it is
    # right to: the generated Airoli register models volumes for B-17's 21 units
    # and records no rights on any of them, which is exactly the gap R015 exists
    # to name. It is a WARNING about this register's completeness, not a title
    # finding, so the run is WARNING overall rather than PASS or FAIL.
    by_id = {f["rule_id"]: f for f in res["findings"]}
    assert by_id["R013"]["status"] == RuleStatus.PASS
    assert by_id["R014"]["status"] == RuleStatus.PASS
    assert by_id["R016"]["status"] == RuleStatus.PASS
    r015 = by_id["R015"]
    assert r015["status"] == RuleStatus.WARNING
    assert "gap in this register" in r015["message"]
    assert len(r015["details"]) == len(dataset["units"])
    assert res["overall_status"] == "WARNING"
    assert res["ownership_report"]["register_populated"] is True
    assert res["ownership_report"]["authoritative"] is False


def test_underground_clash_still_fails_when_unmitigated():
    """An identical clash WITHOUT the protective-sleeve mitigation must FAIL R009."""
    dataset = generate_synthetic_airoli_dataset()
    engine = TopologyQAEngine()
    raw_objects = []
    for obj in dataset["subsurface_objects"]:
        raw_objects.append({k: v for k, v in obj.items() if k != "mitigation"})
    res = engine.run_all_rules(
        parcel_data=dataset["hero_parcel"],
        structure_data=dataset["hero_structure"],
        levels_data=dataset["levels"],
        units_data=dataset["units"],
        subsurface_objects=raw_objects,
    )
    assert res["failed_rules"] >= 1
    r009 = next(f for f in res["findings"] if f["rule_id"] == "R009")
    assert r009["status"] == RuleStatus.FAIL
    assert r009["severity"] == "CRITICAL"


def test_underground_clash_detection():
    detector = UndergroundClashDetector()
    basement_coords = [[145.0, 144.0], [175.0, 144.0], [175.0, 161.0], [145.0, 161.0], [145.0, 144.0]]
    
    # Clash case: pipe passes directly through basement at Z = -3.2m
    res = detector.check_basement_utility_clash(
        basement_polygon_coords=basement_coords,
        basement_min_z=-3.5,
        basement_max_z=0.0,
        utility_start_xyz=[130.0, 150.0, -3.2],
        utility_end_xyz=[190.0, 150.0, -3.2],
        utility_code="PIPE-DRAIN-01",
    )
    assert res["has_clash"] is True
    assert res["severity"] == "CRITICAL"

    # Non-clash case: pipe is deep below basement (e.g. Z = -10.0m)
    res_deep = detector.check_basement_utility_clash(
        basement_polygon_coords=basement_coords,
        basement_min_z=-3.5,
        basement_max_z=0.0,
        utility_start_xyz=[130.0, 150.0, -10.0],
        utility_end_xyz=[190.0, 150.0, -10.0],
        utility_code="METRO-TUNNEL",
    )
    assert res_deep["has_clash"] is False


def test_fsi_calculation():
    fsi_eng = FSIEngine()
    # Plot = 1000 m2, Built-up = 1800 m2 -> FSI = 1.80 <= 2.00 PASS.
    # A verdict requires an authoritative rule *and* authoritative inputs.
    pass_res = fsi_eng.calculate_fsi(
        plot_area_m2=1000.0,
        total_built_up_area_m2=1800.0,
        max_allowed_fsi=2.00,
        jurisdiction_name="TEST-ULB",
        inputs_authoritative=True,
    )
    assert pass_res["calculated_fsi"] == 1.8
    assert pass_res["status"] == "PASS"
    assert pass_res["utilization_pct"] == 90.0
    assert pass_res["assessable"] is True

    # Excess case: Built-up = 2500 m2 -> FSI = 2.50 > 2.00 REVIEW REQUIRED
    review_res = fsi_eng.calculate_fsi(
        plot_area_m2=1000.0,
        total_built_up_area_m2=2500.0,
        max_allowed_fsi=2.00,
        jurisdiction_name="TEST-ULB",
        inputs_authoritative=True,
    )
    assert review_res["calculated_fsi"] == 2.5
    assert review_res["status"] == "REVIEW REQUIRED"
    assert review_res["utilization_pct"] == 125.0


def test_fsi_withholds_verdict_without_a_rule():
    """No permitted-FSI rule on record -> ratio is descriptive, not a finding."""
    res = FSIEngine().calculate_fsi(
        plot_area_m2=1000.0,
        total_built_up_area_m2=2340.0,
        max_allowed_fsi=None,
        jurisdiction_name=None,
        inputs_authoritative=True,
    )
    assert res["calculated_fsi"] == 2.34
    assert res["status"] == "RULE_UNAVAILABLE"
    assert res["utilization_pct"] is None
    assert res["assessable"] is False
    assert "not a compliance determination" in res["disclaimer"]


def test_fsi_withholds_verdict_for_unverified_inputs():
    """A real rule exists but the built-up area is not authoritative."""
    res = FSIEngine().calculate_fsi(
        plot_area_m2=1000.0,
        total_built_up_area_m2=2340.0,
        max_allowed_fsi=2.00,
        jurisdiction_name="TEST-ULB",
        inputs_authoritative=False,
    )
    assert res["calculated_fsi"] == 2.34
    assert res["status"] == "INPUTS_UNVERIFIED"
    # The over-permit ratio must not be dressed up as a compliance percentage.
    assert res["utilization_pct"] is None
    assert res["assessable"] is False
    assert "no over-permit finding" in res["disclaimer"]
