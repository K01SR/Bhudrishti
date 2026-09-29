from typing import Dict, Any
from fastapi import APIRouter, Depends
from app.core.demo_gate import demo_mode_dependency, load_demo_dataset
from app.qa_engine.rules import TopologyQAEngine

router = APIRouter(prefix="/validation", tags=["Topology & Spatial QA"])

_ENGINE = TopologyQAEngine()

# R013-R016 are computed by app.qa_engine.ownership_clash and merged into the
# engine's report by attach_to. Named here so the route can report their scope
# even if a detector is ever dropped from the catalogue.
OWNERSHIP_RULE_IDS = ("R013", "R014", "R015", "R016")


@router.get("/run")
def run_validation(_guard: None = Depends(demo_mode_dependency)):
    """
    Executes rules R001 to R016 against the generated Building B-17 and its
    cadastral relations. Returns individual findings, pass/fail status,
    severity, and clash details.

    R013 to R016 -- the concurrent-claim, volumetric-overlap, untitled-unit and
    disputed/lapsed-title checks -- run in the same pass and their findings sit
    in the same `findings` list, because they read the same unit rows the rest of
    the engine does: a rule that can only be reached by instantiating its own
    detector is a rule a caller silently does not run. `ownership_clash` below
    repeats their scope, the register they compared, and the limit on what they
    can decide, so the disclaimer travels with the findings instead of living in
    a module docstring.

    Gated behind ENABLE_DEMO_MODE, and the dataset is resolved per request
    rather than at import. Two reasons, both learned the hard way:

    The rules run against the generated Airoli dataset, so with the gate shut
    there is nothing to validate. `load_demo_dataset()` then hands back
    structurally empty stand-ins -- `{}` for hero_parcel and `[]` for units --
    and TopologyQAEngine calls `shape(parcel_data.get("polygon_geojson", {}))`
    on them, so `shape()` receives None and the endpoint died with
    `AttributeError: 'NoneType' object has no attribute 'lower'`. A 500 is the
    wrong answer either way: it reads as an outage rather than as "there is no
    dataset here". The gate returns 503 with X-Demo-Mode: disabled instead.

    A module-level snapshot was the same mistake Ask Map made. The dataset was
    captured once at import, so a process that started with the gate open kept
    serving generated records after it was shut, and one that started shut
    stayed permanently empty.
    """
    dataset = load_demo_dataset()
    results = _ENGINE.run_all_rules(
        parcel_data=dataset["hero_parcel"],
        structure_data=dataset["hero_structure"],
        levels_data=dataset["levels"],
        units_data=dataset["units"],
        subsurface_objects=dataset["subsurface_objects"],
    )
    results["ownership_clash"] = _ownership_summary(results.get("ownership_report"))
    return results


def _ownership_summary(report: Any) -> Dict[str, Any]:
    """The title rules' own scope and result, lifted out of the nested report.

    `NO_RECORDS` is passed through rather than being flattened into PASS: an
    empty register never had its rights compared, and a summary that reported it
    as clean would claim a check that did not happen.
    """
    if not isinstance(report, dict):
        return {
            "rule_ids": list(OWNERSHIP_RULE_IDS),
            "ran": False,
            "reason": "the ownership detector did not contribute a report to this run",
        }
    return {
        "rule_ids": list(OWNERSHIP_RULE_IDS),
        "ran": True,
        "total_rules": report.get("total_rules"),
        "passed_rules": report.get("passed_rules"),
        "failed_rules": report.get("failed_rules"),
        "warning_rules": report.get("warning_rules"),
        "overall_status": report.get("overall_status"),
        "register_populated": report.get("register_populated"),
        "as_of": report.get("as_of"),
        "evidence_basis": report.get("evidence_basis"),
        "authoritative": report.get("authoritative"),
        # Identities carried by more than one record: left to the duplicate
        # spatial claim rule rather than reported twice.
        "deferred_to_duplicate_claim": report.get("deferred_to_duplicate_claim"),
        "disclaimer": report.get("disclaimer"),
        "scope_note": (
            "Each of these rules compares the rights recorded on the supplied unit "
            "rows against each other. This platform is not a registry of deeds, so "
            "nothing here establishes who holds title; anything reported is referred "
            "for manual adjudication."
        ),
    }


@router.get("/rules")
def get_rule_catalog():
    """Returns the prototype's rule catalogue, R001 to R016.

    These are rules this project implements, not a published standard. The
    catalogue is served ungated because it is documentation, not data, but a
    description of a rule is not a result: nothing here has been run.
    """
    return [
        {"rule_id": "R001", "name": "Building Enclosure in Parent Parcel", "severity": "CRITICAL", "description": "Building footprint must intersect and be enclosed in parcel."},
        {"rule_id": "R002", "name": "Unit Enclosure in Building Envelope", "severity": "HIGH", "description": "All vertical unit footprints must lie inside the building envelope."},
        {"rule_id": "R003", "name": "Vertical Floor Elevation Non-Overlap", "severity": "HIGH", "description": "Z-intervals of distinct floors must not collide or overlap."},
        {"rule_id": "R004", "name": "Adjacent Unit Spatial Non-Overlap", "severity": "HIGH", "description": "Adjacent units on the same floor level cannot overlap."},
        {"rule_id": "R005", "name": "Floor Bounds Structural Consistency", "severity": "MEDIUM", "description": "Floor slabs cannot exceed structural envelope bounds."},
        {"rule_id": "R006", "name": "Positive Vertical Height Interval", "severity": "HIGH", "description": "Vertical interval must satisfy Z_max > Z_min for all solids."},
        {"rule_id": "R007", "name": "Document vs Calculated Parcel Area Check", "severity": "MEDIUM", "description": "Flag variance between document area and geometry area if > 2%."},
        {"rule_id": "R008", "name": "Multi-Source Building Boundary Concordance", "severity": "MEDIUM", "description": "Ensure spatial alignment (IoU) between GIS cadastre and processed LiDAR."},
        {"rule_id": "R009", "name": "Subterranean Infrastructure Clash Detection", "severity": "CRITICAL", "description": "Detect 3D collisions between basements, utilities, and tunnels."},
        {"rule_id": "R010", "name": "Duplicate Spatial Claim Detection", "severity": "CRITICAL", "description": "Detect overlapping submissions claiming the same unit volume."},
        {"rule_id": "R011", "name": "Duplicate Cadastral Property Detection", "severity": "HIGH", "description": "Ensure unique 3D spatial identity across the state cadastre."},
        {"rule_id": "R012", "name": "OGC Geometric Validity & Solid Closure", "severity": "CRITICAL", "description": "Topological closure, no self-intersections or degenerate faces."},
        {"rule_id": "R013", "name": "Concurrent Active Ownership Claim Detection", "severity": "CRITICAL", "description": "Live ownership rights on one unit whose recorded shares exceed 100%, cannot be checked because a share is unstated, or which sit alongside a testamentary or pending instrument. Undivided shares that add up to 100% are not conflicts.", "evidence_basis": "RECORD_COMPARISON"},
        {"rule_id": "R014", "name": "Volumetric Overlap Between Distinct Registered Units", "severity": "CRITICAL", "description": "Two units with different spatial identities whose 3D volumes intersect while live rights name different parties. Overlaps under one common party are a partition question, not a title conflict.", "evidence_basis": "RECORD_COMPARISON"},
        {"rule_id": "R015", "name": "Recorded Unit Without Recorded Title", "severity": "MEDIUM", "description": "A unit recorded as claimed or approved that carries no right at all. A gap in this register, not evidence that nobody holds title.", "evidence_basis": "RECORD_COMPARISON"},
        {"rule_id": "R016", "name": "Approved Unit With Disputed Or Lapsed Title", "severity": "MEDIUM", "description": "A unit approved while its only live title is disputed or its validity has run out.", "evidence_basis": "RECORD_COMPARISON"},
    ]
