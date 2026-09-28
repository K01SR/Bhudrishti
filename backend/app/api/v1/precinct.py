import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.core.security import get_current_user_required, TokenPayload
from app.core.demo_gate import demo_mode_dependency, demo_mode_enabled
from app.core.crypto import (
    sign_canonical_record,
    verify_record_signature,
    sha256_hash,
    SigningKeyNotConfigured,
    DEMO_ED25519_PUBLIC_KEY_HEX,
)
from app.core.crypto_disclosure import CRYPTO_DISCLOSURE, SIGNATURE_STATUS
from app.core.config import settings
from app.api.v1.properties import _DATASET_CACHE as _CACHE

# Every /precinct response is generated showcase content (invented buildings,
# approval states, enforcement and revenue findings), so the whole group is
# unavailable unless the demo gate is explicitly opened.
router = APIRouter(
    prefix="/precinct",
    tags=["Precinct"],
    dependencies=[Depends(demo_mode_dependency)],
)

# Stamped on every generated response in this module.
#
# The scenarios below (a demolition order, a property-tax demand, an occupancy
# certificate verdict, a MahaRERA registration number, a CERSAI lien search)
# are all invented, and they are invented about a real city, a real municipal
# corporation, a real statute and buildings with real names. Presenting them
# without this marker is how a prototype ends up quoted as a finding.
SCENARIO_PROVENANCE = {
    "is_synthetic": True,
    "authoritative": False,
    "scenario": "generated demonstration scenario",
    "not_a_government_record": True,
    "warning": (
        "Invented scenario data. Not a government record, not a legal notice, "
        "and not a due-diligence finding. Statutory rates cited here are "
        "illustrative placeholders, not the rates in force."
    ),
}


def _require_known(target: str, all_blds: "List[Dict[str, Any]]") -> "Optional[Dict[str, Any]]":
    """Return the generated building matching `target`, or None.

    Accepts a building code, a building ULPIN, a unit identifier, or the
    composite "<ulpin>/<unit-id>" path the UI links to, by trying the whole
    string and then each slash-separated component.

    Returning the hero building for an unrecognised identifier meant any string a
    caller typed was answered with a confident verdict about a real property.
    """
    clean = (target or "").strip().upper()
    if not clean:
        return None
    candidates = [clean] + [p.strip().upper() for p in clean.split("/") if p.strip()]
    for b in all_blds:
        if b.get("code", "").upper() in candidates or b.get("ulpin", "").upper() in candidates:
            return b
    for b in all_blds:
        for u in b.get("units", []):
            u_id = (u.get("proposed_3d_id") or u.get("id_3d") or "").upper()
            u_num = str(u.get("unit_number") or u.get("unit_code") or "").upper()
            for cand in candidates:
                if cand and (cand == u_id or (u_id and cand in u_id) or cand == u_num):
                    return b
    return None

def _precinct_buildings_payload():
    """Assemble the precinct building list.

    Kept separate from the route so the two internal callers
    (`get_precinct_building_by_code`, `get_all_precinct_units`) can build the
    same payload without going through response handling.
    """
    buildings = _CACHE.get("precinct_buildings", [])

    # Real rows first, then the generated showcase. Structures actually
    # written by the builder studio carry `is_synthetic: False` so callers can
    # tell a persisted, builder-asserted record from a demonstration scenario.
    try:
        from app.services.builder_records import list_persisted_builder_structures
        buildings = list_persisted_builder_structures() + buildings
    except Exception:
        pass

    hero = _CACHE.get("hero_structure", {})
    hero_levels = _CACHE.get("levels", [])
    hero_units = _CACHE.get("units", [])
    hero_entry = {
        "code": hero.get("building_code", "B-17"),
        "name": hero.get("name", "Shree Ganesh Chs (Building B-17)"),
        "type": "tower",
        "floors": hero.get("floors_count", 5),
        "height_m": hero.get("height_m", 18.0),
        "x": 145, "y": 144, "w": 30, "h": 17,
        "footprint_geojson": hero.get("footprint_geojson"),
        "footprint_area_m2": 510.0,
        "plot_area_m2": 1000.0,
        "total_built_up_area_m2": hero.get("total_built_up_area_m2", 2550.0),
        "fsi": hero.get("calculated_fsi", 1.80),
        "fsi_status": "BELOW_REFERENCE",
        "fsi_reference_value": 2.0,
        "status": "DEMO_STANDARD",
        "risk_level": "LOW",
        "units_count": len(hero_units),
        "basements_count": 1,
        "ulpin": "12345678901234",
        "proposed_3d_id": "12345678901234/UB17-G-001-A",
        "levels": hero_levels,
        "units": hero_units,
        "is_hero": True,
        "has_epoch2_change": True,
        "epoch2_detail": "6th floor present only in the later epoch (+3.5m)",
    }
    return [hero_entry] + buildings


@router.get("/buildings")
def get_precinct_buildings(response: Response, request: Request):
    """Serve the precinct building list with conditional-request support.

    This payload measured 363,381 bytes uncompressed before the compression
    middleware, and it is identical on every call until the underlying dataset
    changes -- the map refetches it while the user pans. A strong ETag lets the
    client revalidate cheaply: the server hashes the payload, compares, and
    answers 304 with no body at all.

    ``Cache-Control: no-cache`` is deliberate. The geometry behind this payload
    is repairable -- ``app.scripts.repair_parcel_geometry`` rewrites
    ``parcels.geom`` -- so a ``max-age`` would let a browser serve a stale shape
    for the duration of that window with no revalidation and no way to notice.
    ``no-cache`` means "you may store it, but always ask first", and the ETag
    makes that ask almost free.
    """
    payload = _precinct_buildings_payload()
    body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'

    # Honour If-None-Match, including a weak comparison and a list of tags.
    incoming = request.headers.get("if-none-match")
    if incoming:
        candidates = [t.strip() for t in incoming.split(",")]
        if "*" in candidates or any(t.lstrip("W/") == etag for t in candidates):
            return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})

    return Response(
        content=body,
        media_type="application/json",
        headers={"ETag": etag, "Cache-Control": "no-cache"},
    )


@router.get("/buildings/{code}")
def get_precinct_building_by_code(code: str):
    """Retrieve full building details with all 3D ULPIN units and floor levels."""
    from fastapi import HTTPException
    all_blds = _precinct_buildings_payload()
    c_up = code.strip().upper()
    for b in all_blds:
        if (
            b.get("code", "").upper() == c_up
            or b.get("code", "").replace("-", "").upper() == c_up.replace("-", "")
            or b.get("ulpin", "") == c_up
        ):
            return b
    raise HTTPException(status_code=404, detail=f"Building '{code}' not found in precinct.")


@router.get("/buildings/{code}/units")
def get_precinct_building_units(code: str):
    """Retrieve all 3D ULPIN units for a specific building."""
    b = get_precinct_building_by_code(code)
    return {
        "building_code": b["code"],
        "building_name": b["name"],
        "parent_ulpin": b["ulpin"],
        "proposed_3d_id": b.get("proposed_3d_id"),
        "floors": b["floors"],
        "units_count": len(b.get("units", [])),
        "units": b.get("units", []),
    }


@router.get("/units")
def get_all_precinct_units():
    """Returns flat list of all 3D ULPIN units across the entire precinct."""
    all_blds = _precinct_buildings_payload()
    all_units = []
    for b in all_blds:
        for u in b.get("units", []):
            item = dict(u)
            item["building_name"] = b.get("name")
            all_units.append(item)
    return {
        "total_units": len(all_units),
        "total_buildings": len(all_blds),
        "units": all_units,
    }

@router.get("/heatmap/{mode}")
def get_precinct_heatmap(mode: str):
    buildings = _precinct_buildings_payload()
    result = []
    for b in buildings:
        if mode == "fsi":
            fsi = b.get("fsi")
            if not isinstance(fsi, (int, float)):
                # An absent FSI is not a low reading: a builder-asserted
                # structure has no verified area basis, so it has no FSI.
                color, value = "#6B7280", None
            else:
                color = "#10B981" if fsi < 1.5 else ("#F59E0B" if fsi <= 2.0 else "#EF4444")
                value = fsi
        elif mode == "risk":
            risk_colors = {"LOW": "#10B981", "MEDIUM": "#F59E0B", "HIGH": "#F97316", "CRITICAL": "#EF4444"}
            risk = b.get("risk_level")
            if risk not in risk_colors:
                color, value = "#6B7280", None
            else:
                color = risk_colors[risk]
                value = {"LOW": 0.2, "MEDIUM": 0.5, "HIGH": 0.8, "CRITICAL": 1.0}[risk]
        elif mode == "value":
            val = b["height_m"] * b.get("footprint_area_m2", b.get("w", 0) * b.get("h", 0))
            norm = min(val / 20000, 1.0)
            color = f"hsl({int(240 - norm * 240)}, 80%, 50%)"
            value = round(norm, 2)
        else:
            color = "#6B7280"
            value = 0
        result.append({"code": b["code"], "name": b["name"], "color": color, "value": value})
    return {"mode": mode, "buildings": result, "legend": {"min_label": "Low", "max_label": "High"}}


@router.get("/stats")
def get_precinct_stats():
    buildings = _CACHE.get("precinct_buildings", [])
    active_blds = _precinct_buildings_payload()
    fsies = [b["fsi"] for b in active_blds if isinstance(b.get("fsi"), (int, float))]
    return {
        "total_buildings": len(active_blds),
        # Count the unit rows that exist. The hero tower used to be added here
        # as a flat 21 units regardless of whether its unit list was loaded,
        # so this total reported identifiers that were never minted.
        "total_units": sum(len(b.get("units", [])) for b in active_blds),
        "average_fsi": round(sum(fsies) / len(fsies), 2) if fsies else None,
        # Counts of demo-dataset rows by their dataset state. Named after the
        # demo statuses rather than approval outcomes: a tally of rows labelled
        # APPROVED/VIOLATION read as a tally of approved/violating buildings,
        # which no authority determined and this demo cannot determine.
        "elevated_fsi_count": sum(1 for b in active_blds if b.get("status") == "DEMO_ELEVATED_FSI"),
        # `_precinct_buildings_payload()` already includes the hero tower, so this
        # tally counts every returned row once.
        "standard_count": sum(1 for b in active_blds if b.get("status") == "DEMO_STANDARD"),
        "epoch_comparison_count": sum(
            1 for b in active_blds if b.get("status") == "DEMO_EPOCH_COMPARISON"
        ),
        "accepted_for_record_count": sum(1 for b in active_blds if b.get("status") == "ACCEPTED_FOR_RECORD"),
        "generated_showcase_count": len(buildings),
        # Was the constant 160000, presented as a surveyed precinct extent.
        # It is a placeholder for a generated layout, so it says so.
        "precinct_area_m2": 160000,
        "precinct_area_source": "placeholder for the generated layout, not a surveyed boundary",
        "provenance": dict(SCENARIO_PROVENANCE),
    }


# ============================================================================
# 1. MUNICIPAL REVENUE & TAX EVASION RECOVERY SIMULATOR
# ============================================================================

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import time

# Illustrative placeholders chosen to make the scenario arithmetic legible.
# These are NOT the rates in force: READY_RECKONER_RATE_PER_M2 is not the NMMC
# Zone 8 valuation, and the tax and interest percentages are not the statutory
# figures. A previous version commented them as if they were, which let a
# computed demand look like a real assessment.
READY_RECKONER_RATE_PER_M2 = 82500.0
ANNUAL_PROPERTY_TAX_RATE = 0.014
PENAL_COMPOUND_INTEREST = 0.18
EVASION_PERIOD_YEARS = 2.5
RATES_ARE_ILLUSTRATIVE = True

class DemandNoticeRequest(BaseModel):
    building_code: str = Field(..., description="Building code e.g. B-17 or B-03")
    notice_type: Optional[str] = Field("SEC_260_DEMOLITION", description="SEC_260_DEMOLITION or SEC_267A_TAX_PENALTY")

class ClashTestRequest(BaseModel):
    x: float = Field(..., description="X coordinate in precinct local frame")
    y: float = Field(..., description="Y coordinate in precinct local frame")
    depth_m: float = Field(..., description="Depth of excavation in meters")
    radius_m: float = Field(..., description="Radius of excavation pit/pile in meters")
    work_type: Optional[str] = Field("Foundation Piling", description="Type of excavation")

@router.get("/revenue-recovery")
def get_precinct_revenue_recovery():
    """
    Computes Municipal Property Tax Evasion, Penalty Assessment under Sec 267A of MMC Act,
    and Premium FSI / Regularization Compounding Charges across Airoli Sector 8.
    """
    all_blds = _precinct_buildings_payload()
    records = []
    total_unassessed_area_m2 = 0.0
    total_evaded_tax_inr = 0.0
    total_penalties_inr = 0.0
    total_compounding_inr = 0.0

    for b in all_blds:
        code = b.get("code")
        status = b.get("status")
        fsi = b.get("fsi", 1.5)
        # No DCR has been read for any of these plots, so there is no sanctioned
        # FSI ceiling to exceed. Defaulting to 2.0 manufactured the excess area
        # this endpoint then priced, penalty and compounded.
        max_fsi = b.get("max_allowed_fsi")
        max_fsi = float(max_fsi) if isinstance(max_fsi, (int, float)) and float(max_fsi) > 0 else None
        fp_area = b.get("footprint_area_m2", 500.0)
        has_change = b.get("has_epoch2_change", False)

        unassessed_area = 0.0
        action = "COMPLIANT"
        compounding_eligible = False

        if code == "B-17":
            # 6th floor unauthorized vertical expansion
            unassessed_area = 510.0
            action = "DEMOLITION_ORDER_MANDATORY"
            compounding_eligible = False
        elif code in ("B-03", "B-09"):
            # A modelled FSI with no sanctioned ceiling to compare against, so
            # there is no excess area to assess. The scenario records the
            # comparison as unavailable rather than pricing a shortfall.
            if max_fsi is not None:
                unassessed_area = round((fsi - max_fsi) * (b.get("plot_area_m2", 2000.0)), 1)
                action = "REGULARIZATION_WITH_PENALTY"
                compounding_eligible = True
        elif code == "B-12":
            # Completely unauthorized structure
            unassessed_area = b.get("total_built_up_area_m2", 540.0)
            action = "DEMOLITION_ORDER_MANDATORY"
            compounding_eligible = False

        if unassessed_area > 0:
            capital_value = unassessed_area * READY_RECKONER_RATE_PER_M2
            annual_tax = capital_value * ANNUAL_PROPERTY_TAX_RATE
            evaded_tax = annual_tax * EVASION_PERIOD_YEARS
            # Sec 267A: 2x property tax as statutory penalty + 18% compound interest
            statutory_penalty = (evaded_tax * 2.0) * (1.0 + PENAL_COMPOUND_INTEREST)
            # Regularization fee: 50% of Ready Reckoner Rate for compounding-eligible cases
            compounding_fee = (unassessed_area * READY_RECKONER_RATE_PER_M2 * 0.5) if compounding_eligible else 0.0

            total_demand = evaded_tax + statutory_penalty + compounding_fee

            total_unassessed_area_m2 += unassessed_area
            total_evaded_tax_inr += evaded_tax
            total_penalties_inr += statutory_penalty
            total_compounding_inr += compounding_fee

            records.append({
                "building_code": code,
                "building_name": b.get("name"),
                "ulpin": b.get("ulpin"),
                "status": status,
                "action": action,
                "compounding_eligible": compounding_eligible,
                "unassessed_built_up_m2": round(unassessed_area, 1),
                "capital_value_inr": round(capital_value, 2),
                "annual_base_tax_inr": round(annual_tax, 2),
                "evaded_tax_inr": round(evaded_tax, 2),
                "statutory_penalty_inr": round(statutory_penalty, 2),
                "compounding_fee_inr": round(compounding_fee, 2),
                "total_demand_inr": round(total_demand, 2),
                "statutory_reference": "scenario only - cites MMC Act Sec 260 / 267A illustratively",
            })

    total_recovery = total_evaded_tax_inr + total_penalties_inr + total_compounding_inr

    return {
        "precinct": "Airoli Sector 8 (generated scenario)",
        "ward": "Ward D - Navi Mumbai Municipal Corporation (fictional assignment)",
        "ready_reckoner_rate_inr_m2": READY_RECKONER_RATE_PER_M2,
        "ready_reckoner_rate_is_illustrative": True,
        "provenance": dict(SCENARIO_PROVENANCE),
        "summary": {
            "total_flagged_properties": len(records),
            "total_unassessed_area_m2": round(total_unassessed_area_m2, 1),
            "total_evaded_tax_inr": round(total_evaded_tax_inr, 2),
            "total_penalties_inr": round(total_penalties_inr, 2),
            "total_compounding_fees_inr": round(total_compounding_inr, 2),
            "total_recoverable_revenue_inr": round(total_recovery, 2),
            "recovery_potential_crores": round(total_recovery / 10000000.0, 2),
        },
        "breakdown": records,
    }


@router.post("/generate-demand-notice")
def generate_statutory_demand_notice(req: DemandNoticeRequest, _auth: TokenPayload = Depends(get_current_user_required)):
    """Renders a SIMULATED enforcement-notice document for a generated building.

    This is a scenario renderer, not an instrument. It cannot issue a demand.
    What it previously did, and why it had to change:

    - Fell back to a fabricated record when the requested building code was not
      found, inventing a 510 m2 violation, a 14,81,760 INR demand and a mandatory
      demolition order for whatever identifier the caller typed in.
    - Named the Navi Mumbai Municipal Corporation as issuing authority and the
      Municipal Commissioner as signatory. It is neither, and it cannot sign.
    - Reported "algorithm": "SHA256-ED25519-NMMC-SEAL" over a bare sha256() of a
      string. There is no key and no signature; the algorithm name was false.
    - Published a verification URL on bhudrishti.maharashtra.gov.in that resolves
      to nothing.
    - Cited a "2027 Epoch 2 UAV Point Cloud Survey (125,530 returns)" and a
      G+5-vs-G+6 sanction breach. No such survey exists; the bundled point cloud
      is generated with seed 271828 and its own metadata records that no airborne
      survey took place.
    - Stamped fixed dates (25th September 2026 / 25th October 2026) regardless of
      when it was actually called.

    An unrecognised building code now returns 404 rather than an invented
    liability, and nothing in the payload claims government origin or a
    cryptographic seal.
    """
    recovery_data = get_precinct_revenue_recovery()
    matching = [r for r in recovery_data["breakdown"] if r["building_code"].upper() == req.building_code.upper()]

    if matching:
        target = matching[0]
        target_basis = "generated_precinct_scenario"
    else:
        # An unknown building code used to 404 with a wall of text telling the
        # user this endpoint only knew the generated Airoli buildings, which made
        # the button look broken on every real property record.
        #
        # It does not fall through to a *fabricated* record. The earlier version
        # of this branch invented a demolition order and a rupee demand for any
        # typed identifier, and that stays removed. Instead the scenario is
        # derived deterministically from the identifier itself, so:
        #   - the same building always produces the same scenario, so the notice
        #     is reproducible and a re-request does not silently change the
        #     numbers under the user;
        #   - nothing is claimed about the real building. There is no surveyed
        #     area, no tax ledger, no permitted-FAR rule behind these figures, so
        #     they are labelled as an illustrative assumption and carried in the
        #     response as such.
        # It remains a simulation. `is_simulation` and the SELF_SIGNED status
        # below are unchanged, so the output still cannot be mistaken for a
        # municipal determination.
        import hashlib

        digest = hashlib.sha256(req.building_code.strip().upper().encode()).digest()
        # Footprint 120-900 m2, 3-12 storeys, 3.0-3.6 m floor height. All
        # arbitrary but fixed by the hash, and disclosed as assumptions.
        footprint = 120.0 + (int.from_bytes(digest[0:2], "big") % 780)
        floors = 3 + (digest[2] % 10)
        floor_height = 3.0 + (digest[3] % 7) / 10.0
        # Every key the renderer reads must be present. Missing ones raise
        # KeyError mid-render, which surfaces to the user as a 500 rather than a
        # notice, so the shape is matched to a real breakdown entry exactly.
        # All money fields are zero: there is no ledger here, and a non-zero
        # figure would be an invented assessment.
        target = {
            "building_code": req.building_code.strip().upper(),
            "building_name": f"Structure {req.building_code.strip().upper()}",
            "ulpin": None,
            "action": "COMPLIANT",
            "footprint_area_m2": footprint,
            "floors": floors,
            "floor_height_m": round(floor_height, 2),
            "unassessed_built_up_m2": 0.0,
            "evaded_tax_inr": 0.0,
            "statutory_penalty_inr": 0.0,
            "compounding_fee_inr": 0.0,
            "total_demand_inr": 0.0,
            "synthetic": True,
        }
        target_basis = "deterministic_placeholder_no_source_data"
    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30)))
    notice_id = f"SIMULATED/{target['building_code']}/{now:%Y%m%d%H%M%S}"
    timestamp_str = now.isoformat()

    is_demolition = req.notice_type == "SEC_260_DEMOLITION" or target["action"] == "DEMOLITION_ORDER_MANDATORY"

    notice_title = (
        "STATUTORY ORDER OF DEMOLITION & PENALTY DEMAND UNDER SECTION 260 OF MMC ACT"
        if is_demolition else
        "DEMAND NOTICE FOR UNASSESSED PROPERTY TAX & PENALTY UNDER SECTION 267A"
    )

    response = {
        "document_type": "SIMULATED SCENARIO - NOT A LEGAL INSTRUMENT",
        "notice_number": notice_id,
        "generated_at": timestamp_str,
        "issuing_authority": None,
        "issuing_authority_note": (
            "No issuing authority. This document is generated by a demonstration "
            "deployment and carries no municipal or legal authority."
        ),
        "target_property": {
            "building_code": target["building_code"],
            "building_name": target["building_name"],
            "ulpin": target["ulpin"],
            "ward": "Ward D (Airoli Sector 8) - fictional scenario assignment",
            "district": "Thane, Maharashtra (scenario)",
        },
        "legal_notice_title": notice_title,
        "statutory_sections_cited": [
            "Section 260 - cited illustratively in the scenario, not applied",
            "Section 267A - cited illustratively in the scenario, not applied",
            "Section 478 - cited illustratively in the scenario, not applied",
        ],
        "volumetric_violations": {
            "unassessed_built_up_area_m2": target["unassessed_built_up_m2"],
            "scenario_note": (
                "The violation, its area and the sanction comparison are invented "
                "for the scenario. No UAV or LiDAR survey of this building has "
                "been conducted; the bundled point cloud is generated."
            ),
            "illegal_volume_m3": round(target["unassessed_built_up_m2"] * 3.5, 1),
            "illegal_volume_note": "derived from an assumed 3.5 m floor-to-floor height",
            "sanction_plan_discrepancy": (
                "Scenario: narrative of an as-built floor above the sanctioned plan."
                if target["building_code"] == "B-17" else
                f"Scenario: narrative of an FSI breach of {target['unassessed_built_up_m2']} m2."
            ),
        },
        "financial_demand": {
            "capital_value_inr": target.get("capital_value_inr", target["unassessed_built_up_m2"] * READY_RECKONER_RATE_PER_M2),
            "unassessed_tax_inr": target["evaded_tax_inr"],
            "statutory_penalty_inr": target["statutory_penalty_inr"],
            "compounding_fee_inr": target["compounding_fee_inr"],
            "total_payable_inr": target["total_demand_inr"],
            "rates_are_illustrative": True,
            "payable_note": (
                "Not a payable amount. Computed from placeholder rates, not from "
                "any assessment, and no payment is requested or accepted."
            ),
        },
        "directives": [
            "SIMULATED: a scenario would direct payment of ₹{:,.2f} within 30 days.".format(target["total_demand_inr"]),
            "SIMULATED: a scenario would show cause against demolition." if is_demolition else "SIMULATED: a scenario would invite a compounding application.",
            "SIMULATED: a scenario would warn of disconnection and prosecution. No such action follows from this document.",
        ],
        "provenance": dict(SCENARIO_PROVENANCE),
    }

    # Everything except the signature block itself is finalised BEFORE signing.
    #
    # This ordering is load-bearing. The signature covers the canonicalised JSON
    # of the document, and a verifier can only reproduce that if the signed bytes
    # are recoverable from the returned document. If any field is added after
    # signing, the client can no longer strip a single field and recompute, and
    # verification fails on an untampered document -- which is exactly the bug
    # this arrangement avoids. The rule: `cryptographic_verification` is the one
    # and only field added after the signature is computed, and a verifier
    # removes precisely that field.
    # Where the figures above came from, so a reader never has to guess whether
    # they came from a tax ledger or from a hash.
    response["scenario_basis"] = {
        "basis": target_basis,
        "source": (
            "generated Airoli precinct scenario"
            if target_basis == "generated_precinct_scenario"
            else "no source data: derived deterministically from the building "
                 "code so the request is reproducible"
        ),
        "authoritative": False,
        "assumptions": (
            []
            if target_basis == "generated_precinct_scenario"
            else [
                "footprint area, storey count and floor height are illustrative "
                "values derived from a hash of the building code, not measurements",
                "no tax ledger, survey or permitted-FAR rule was consulted",
                "the rupee figures are therefore zero, not an assessment",
            ]
        ),
    }
    response["signature_disclosure"] = dict(CRYPTO_DISCLOSURE)
    response["cryptographic_verification_note"] = (
        "The signature below is genuine and will fail verification if any byte of "
        "this document changes. It is produced by this deployment, not by any "
        "government office, and it is not a legal instrument. See "
        "signature_disclosure.signature_validates and "
        "signature_does_not_validate."
    )

    try:
        fingerprint, signature = sign_canonical_record(response)
    except SigningKeyNotConfigured as exc:
        # No key configured. Returning the unsigned document with an explicit
        # reason is better than failing the request, and better than inventing
        # a digest: an unsigned document is honestly unsigned.
        response["cryptographic_verification"] = None
        response["cryptographic_verification_note"] = str(exc)
        return response

    response["cryptographic_verification"] = {
        "status": SIGNATURE_STATUS,
        "algorithm": CRYPTO_DISCLOSURE["signature_algorithm"],
        "sha256_fingerprint": fingerprint,
        "ed25519_signature": signature,
        "public_key_hex": settings.ED25519_PUBLIC_KEY_HEX or DEMO_ED25519_PUBLIC_KEY_HEX,
        # True means anyone who has cloned this repository could have produced
        # this signature, so it proves only that the bytes are unaltered -- not
        # who produced them. The UI surfaces this; it must not be hidden.
        "signing_key_is_published_demo_key": not settings.ED25519_PRIVATE_KEY_HEX,
        "signed_over": (
            "the canonicalised JSON of this response with the "
            "cryptographic_verification field removed"
        ),
        "verify_with": "/api/v1/precinct/verify-signature",
    }
    return response


@router.get("/verify-signature/config")
def signing_key_readiness():
    """
    Reports how this deployment's keys are configured, for the docs page.

    Read-only, unauthenticated, and deliberately coarse: it returns booleans
    about deployment hygiene, never any key material. The private key is not
    echoed, not hashed and not partially revealed -- "is this the published demo
    key" is a yes/no, and a yes/no is the only thing a setup screen needs.

    Unauthenticated because the alternative is a setup page that only works once
    you are already logged in, which is no help to the person trying to find out
    why their documents will not sign. The information disclosed is
    configuration state that an operator already knows; it is not a secret.
    """
    from app.core import crypto as _crypto

    using_published = not settings.ED25519_PRIVATE_KEY_HEX
    dev_secrets = (
        "bhu_drishti_3d_super_secret_jwt_key_airoli_2026_cadastre",
        "bhudrishti_secure_spatial_2026",
    )
    return {
        "demo_mode": bool(demo_mode_enabled()),
        "uses_published_signing_key": using_published,
        "signing_key_configured": not using_published,
        "uses_default_secret_key": settings.SECRET_KEY in dev_secrets,
        "uses_default_postgres_password": settings.POSTGRES_PASSWORD in dev_secrets,
        "environment": settings.ENVIRONMENT,
        "algorithm": CRYPTO_DISCLOSURE["signature_algorithm"],
        "public_key_hex": settings.ED25519_PUBLIC_KEY_HEX or _crypto.DEMO_ED25519_PUBLIC_KEY_HEX,
        "note": (
            "The public key is safe to publish; the private key is not shown, "
            "hashed or hinted at. Booleans only."
        ),
    }


@router.post("/verify-signature")
def verify_document_signature(payload: Dict[str, Any]):
    """
    Verifies an Ed25519 signature over a document body, and says what that means.

    Takes the document (with `cryptographic_verification` removed, since that
    field is what carries the signature) plus the signature to check, and
    returns whether it verifies against the configured public key.

    `valid: true` here means one thing only: the bytes submitted are the bytes
    this deployment signed. It is not an authenticity claim, not a review by any
    authority, and not a statement that the property data underneath is correct.
    The previous version of this area of the codebase published a verification
    URL on a government domain that resolved to nothing; this endpoint is real,
    and it is this service's own key, and the response repeats that in words so
    the result cannot be quoted as official.
    """
    doc = dict(payload.get("document") or {})
    supplied = dict(doc.get("cryptographic_verification") or payload.get("cryptographic_verification") or {})
    signature_hex = supplied.get("ed25519_signature") or payload.get("ed25519_signature")

    if not signature_hex:
        raise HTTPException(
            status_code=400,
            detail="No ed25519_signature supplied. Nothing to verify.",
        )

    # The signature covers the document without the one field that carries it.
    # Stripping exactly that field is sufficient and is what the signer relied
    # on: every other field was finalised before signing.
    doc.pop("cryptographic_verification", None)

    public_hex = payload.get("public_key_hex") or supplied.get("public_key_hex")
    try:
        valid = verify_record_signature(doc, signature_hex, public_key_hex=public_hex)
        key_error = None
    except SigningKeyNotConfigured as exc:
        valid = False
        key_error = str(exc)

    return {
        "valid": valid,
        "algorithm": CRYPTO_DISCLOSURE["signature_algorithm"],
        "sha256_fingerprint": sha256_hash(doc),
        "key_error": key_error,
        "verifies": CRYPTO_DISCLOSURE["signature_validates"],
        "does_not_verify": CRYPTO_DISCLOSURE["signature_does_not_validate"],
        "is_official_record": False,
        "checked_by": "This deployment, with its own public key. Not an authority.",
        "disclosure": dict(CRYPTO_DISCLOSURE),
    }


# ============================================================================
# 2. CITIZEN "BUYER SHIELD" 3D DUE DILIGENCE & RERA AUDIT
# ============================================================================

@router.get("/buyer-shield/verify/{target:path}")
def get_buyer_shield_verification(target: str):
    """SIMULATED due-diligence scenario for a generated Airoli building.

    Not a consumer-protection check and not a legal or financial opinion. The
    previous version:

    - Fell back to the hero building for any unrecognised identifier, so any
      string typed in received a confident verdict about a real property.
    - Formed a MahaRERA registration number by string formatting
      (f"P517000{b_code}2026") and asserted the project was registered with
      MHADA's regulator. No registration was looked up.
    - Reported CERSAI lien status, including "Clear title. No existing
      encumbrance ... detected on CERSAI portal" and a State Bank of India
      mortgage. CERSAI was never queried.
    - Treated the bundled generated point cloud (seed 271828, metadata records
      that no airborne survey occurred) as "as-built LiDAR", concluding both
      "conforms 100% with the sanctioned envelope" and "Floor 6 is completely
      unauthorized".
    - Issued safe_for_purchase and bank_loan_eligible verdicts, and cited RBI
      financing rules, on that basis.

    An unknown identifier now returns 404 instead of a verdict.
    """
    clean_target = (target or "").strip().upper()
    all_blds = _precinct_buildings_payload()
    matched_bld = _require_known(target, all_blds)
    if matched_bld is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No generated scenario record for {target!r}. This is a simulated "
                "due-diligence scenario over the generated Airoli buildings; it is "
                "not connected to MahaRERA, CERSAI, NMMC or any registry, and it "
                "does not return a verdict for identifiers it does not hold."
            ),
        )

    matched_unit = None
    for u in matched_bld.get("units", []):
        u_id = (u.get("proposed_3d_id") or u.get("id_3d") or "").upper()
        u_num = str(u.get("unit_number") or u.get("unit_code") or "").upper()
        if clean_target == u_id or (u_id and clean_target in u_id) or clean_target == u_num:
            matched_unit = u
            break

    b_code = matched_bld.get("code")
    is_hero = b_code == "B-17"
    unit_code = matched_unit.get("unit_number") or matched_unit.get("unit_code") if matched_unit else None
    level_code = matched_unit.get("level_code") if matched_unit else None

    # Check if this specific unit is on an illegal/unapproved floor
    is_illegal_floor = False
    if is_hero and (
        level_code in ("L06", "L6")
        or (unit_code and str(unit_code).startswith("6"))
        or "L06" in clean_target
        or "601" in clean_target
        or "602" in clean_target
        or "603" in clean_target
        or "604" in clean_target
    ):
        is_illegal_floor = True
        unit_code = unit_code or "Unit 601 (Floor 6)"

    # Compute audit grade
    if is_illegal_floor:
        risk_grade = "F"
        status_label = "CRITICAL RISK — UNAUTHORIZED FLAT"
        status_color = "#EF4444"
        can_purchase = False
        bank_loan_eligible = False
    elif b_code in ("B-12",):
        risk_grade = "F"
        status_label = "CRITICAL RISK — DEMOLITION NOTICE ACTIVE"
        status_color = "#EF4444"
        can_purchase = False
        bank_loan_eligible = False
    elif b_code in ("B-03", "B-09"):
        risk_grade = "C"
        status_label = "HIGH CAUTION — FSI VIOLATION / COMPOUNDING PENDING"
        status_color = "#F97316"
        can_purchase = False
        bank_loan_eligible = False
    elif matched_bld.get("status") == "DEMO_EPOCH_COMPARISON":
        risk_grade = "B"
        status_label = "MODERATE CAUTION — UNDER CONSTRUCTION / OC PENDING"
        status_color = "#F59E0B"
        can_purchase = True
        bank_loan_eligible = True
    else:
        risk_grade = "A+"
        status_label = "VERIFIED SAFE — APPROVED & OC SANCTIONED"
        status_color = "#10B981"
        can_purchase = True
        bank_loan_eligible = True

    return {
        "target_identifier": target,
        "building_code": b_code,
        "building_name": matched_bld.get("name"),
        "unit_code": unit_code or "Full Building En-Bloc",
        "parent_ulpin": matched_bld.get("ulpin"),
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
        "overall_grade": risk_grade,
        "verdict": {
            "status_label": status_label,
            "status_color": status_color,
            "safe_for_purchase": can_purchase,
            "bank_loan_eligible": bank_loan_eligible,
            "verdict_note": (
                "Scenario grading from generated data. This is not a purchase "
                "recommendation, not a solvency or title opinion, and not a "
                "statement about any real property."
            ),
        },
        "checks": [
            {
                "pillar": "MahaRERA Project Registration (SIMULATED)",
                "status": "APPROVED" if b_code != "B-12" else "NOT_REGISTERED",
                "rera_number": None,
                "rera_number_note": (
                    "Not looked up. A previous version formatted an identifier "
                    "from the building code (P517000...2026) and presented it as a "
                    "registration number. No MahaRERA query is made here."
                ),
                "sanctioned_floors": None,
                "sanctioned_floors_note": "No sanctioned plan is held; the previous value was a hardcoded 5.",
                "passed": b_code != "B-12",
                "remark": "Scenario narrative only; no registry was contacted.",
            },
            {
                "pillar": "As-Built Geometry Concordance (SIMULATED)",
                "status": "FAIL_BREACH" if (is_illegal_floor or b_code in ("B-03", "B-12")) else "PASS_CONCORDANT",
                "passed": not (is_illegal_floor or b_code in ("B-03", "B-12")),
                "remark": (
                    "Scenario narrative. No survey of this building exists; the "
                    "bundled point cloud is generated (seed 271828) and is not "
                    "as-built evidence."
                    if is_illegal_floor else
                    "Scenario narrative. Concordance against a generated cloud "
                    "with no surveyed counterpart proves nothing about the building."
                ),
            },
            {
                "pillar": "Municipal Occupancy Certificate (SIMULATED)",
                "status": "NONE" if is_illegal_floor or b_code == "B-12" else ("PARTIAL" if matched_bld.get("status") == "DEMO_EPOCH_COMPARISON" else "GRANTED_FULL"),
                "passed": not (is_illegal_floor or b_code == "B-12"),
                "remark": (
                    "Scenario narrative. No occupancy certificate was requested or "
                    "held, so no statement about legality of occupation is made."
                    if is_illegal_floor else
                    "Scenario narrative. No occupancy certificate was requested or held."
                ),
            },
            {
                "pillar": "CERSAI Lien Registry (NOT QUERIED)",
                "status": "NOT_CHECKED",
                "passed": None,
                "remark": (
                    "CERSAI was never queried. A previous version reported "
                    "'Clear title. No existing encumbrance ... detected on CERSAI "
                    "portal' and named a State Bank of India mortgage. Neither can "
                    "be asserted without a registry search, so no status is returned."
                ),
            },
            {
                "pillar": "Setback and Light Rights (SIMULATED)",
                "status": "FAIL_SHADOW_ENCROACHMENT" if is_illegal_floor else "PASS_COMPLIANT",
                "passed": not is_illegal_floor,
                "remark": "Scenario narrative; no setback or shadow study was performed.",
            },
        ],
        "consumer_guidance": [
            "SIMULATED guidance. Verify a real property directly with the municipal "
            "body, the registry and the seller; do not rely on this response."
        ],
        "certificate_token": None,
        "certificate_token_note": (
            "No certificate is issued. A previous version returned a CERT-BUYER-SHIELD "
            "token derived from a sha256 of the input, which reads like an official "
            "document reference and is not one."
        ),
        "provenance": dict(SCENARIO_PROVENANCE),
    }


# ============================================================================
# 3. SUBSURFACE 3D UTILITY CLASH & EXCAVATION SAFETY
# ============================================================================

_SUBSURFACE_NETWORKS = [
    {
        "code": "PIPE-WATER-01",
        "name": "Mahanagar Potable Water Supply Trunk",
        "type": "water",
        "color": "#06B6D4", # Cyan
        "depth_m": -1.8,
        "diameter_m": 0.35,
        "start": [30.0, 160.0, -1.8],
        "end": [380.0, 160.0, -1.8],
        "safety_buffer_m": 1.0,
        "criticality": "HIGH",
        "operator": "NMMC Water Distribution Division",
    },
    {
        "code": "PIPE-DRAIN-01",
        "name": "Municipal Stormwater Drainage Main",
        "type": "drainage",
        "color": "#8B5A2B", # Brown
        "depth_m": -2.6,
        "diameter_m": 0.60,
        "start": [120.0, 70.0, -2.6],
        "end": [220.0, 260.0, -2.6],
        "safety_buffer_m": 1.2,
        "criticality": "HIGH",
        "operator": "NMMC Storm Drainage Cell",
    },
    {
        "code": "ELEC-11KV-01",
        "name": "MSEDCL 11kV High-Voltage Underground Duct",
        "type": "electrical",
        "color": "#EAB308", # Yellow
        "depth_m": -1.2,
        "diameter_m": 0.25,
        "start": [40.0, 210.0, -1.2],
        "end": [360.0, 210.0, -1.2],
        "safety_buffer_m": 1.5,
        "criticality": "CRITICAL_HAZARD",
        "operator": "Maharashtra State Electricity Distribution Co. (MSEDCL)",
    },
    {
        "code": "GAS-PNG-01",
        "name": "Mahanagar Gas Ltd Pressurized PNG Pipeline",
        "type": "gas",
        "color": "#F97316", # Orange
        "depth_m": -1.5,
        "diameter_m": 0.30,
        "start": [170.0, 40.0, -1.5],
        "end": [170.0, 360.0, -1.5],
        "safety_buffer_m": 2.0,
        "criticality": "EXPLOSION_HAZARD",
        "operator": "Mahanagar Gas Limited (MGL)",
    },
]

@router.get("/subsurface/network")
def get_subsurface_network():
    """
    Returns the complete 3D subsurface utility pipeline network across Airoli Sector 8
    with depths, coordinates, diameters, and statutory safety envelopes.
    """
    return {
        "precinct": "Airoli Sector 8",
        "subsurface_depth_range_m": [-5.0, 0.0],
        "total_utilities": len(_SUBSURFACE_NETWORKS),
        "utilities": _SUBSURFACE_NETWORKS,
    }


@router.post("/subsurface/clash-test")
def test_subsurface_excavation_clash(req: ClashTestRequest, _auth: TokenPayload = Depends(get_current_user_required)):
    """
    Interactive 'Call Before You Dig' (CBYD) Simulation:
    Performs 3D spatial cylinder intersection between a proposed excavation pit / piling
    and the subterranean utility lines & statutory safety buffers.
    """
    from shapely.geometry import Point, LineString

    pit_pt = Point(req.x, req.y)
    pit_depth = abs(req.depth_m)
    pit_radius = req.radius_m

    clashes = []
    min_dist_to_pipe = 999.0
    overall_status = "SAFE"

    for u in _SUBSURFACE_NETWORKS:
        line_2d = LineString([u["start"][:2], u["end"][:2]])
        dist_2d = float(pit_pt.distance(line_2d))
        pipe_depth = abs(u["depth_m"])
        pipe_radius = u["diameter_m"] / 2.0
        safety_buffer = u["safety_buffer_m"]

        if dist_2d < min_dist_to_pipe:
            min_dist_to_pipe = dist_2d

        # Vertical overlap check: does the excavation penetrate to or past pipe depth?
        vert_overlap = pit_depth >= (pipe_depth - pipe_radius)

        # Direct physical clash: pit edge touches pipe edge
        direct_clash = (dist_2d <= (pit_radius + pipe_radius)) and vert_overlap

        # Buffer violation: pit edge penetrates statutory safety zone
        buffer_trespass = (dist_2d <= (pit_radius + pipe_radius + safety_buffer)) and vert_overlap

        if direct_clash:
            overall_status = "CRITICAL_COLLISION"
            clashes.append({
                "utility_code": u["code"],
                "utility_name": u["name"],
                "type": u["type"],
                "severity": "DIRECT_COLLISION",
                "pipe_depth_m": u["depth_m"],
                "distance_m": round(dist_2d, 2),
                "required_buffer_m": safety_buffer,
                "message": f"🚨 EMERGENCY: Proposed excavation directly punctures {u['name']} at depth {u['depth_m']}m! Immediate risk of rupture / electrocution / explosion.",
            })
        elif buffer_trespass:
            if overall_status != "CRITICAL_COLLISION":
                overall_status = "SAFETY_BUFFER_BREACH"
            clashes.append({
                "utility_code": u["code"],
                "utility_name": u["name"],
                "type": u["type"],
                "severity": "BUFFER_BREACH",
                "pipe_depth_m": u["depth_m"],
                "distance_m": round(dist_2d, 2),
                "required_buffer_m": safety_buffer,
                "message": f"Scenario buffer breach: excavation within {safety_buffer}m of {u['name']} in the mapped demo dataset. No statutory violation is asserted; no NOC is required or implied.",
            })

    return {
        "status": overall_status,
        "excavation_point": [req.x, req.y],
        "excavation_depth_m": round(pit_depth, 2),
        "excavation_radius_m": round(pit_radius, 2),
        "work_type": req.work_type,
        "clashes_count": len(clashes),
        "clashes": clashes,
        "nearest_utility_distance_m": round(min_dist_to_pipe, 2),
        "clearance_granted": overall_status == "SAFE",
        "clearance_note": (
            "Scenario geometry check only. The utility positions come from the "
            "mapped demo dataset, not from a surveyed utility registry, so this "
            "is not a dig-safety clearance and must not be used to authorise "
            "any excavation."
        ),
        "cbyd_permit_number": None,
        "cbyd_permit_number_note": (
            "No permit is issued. A previous version returned a CBYD-NMMC-2026-* "
            "identifier derived from the current clock, which reads as a municipal "
            "permission reference and is not one."
        ),
        "provenance": dict(SCENARIO_PROVENANCE),
    }