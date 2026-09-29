from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from app.core.demo_gate import demo_mode_dependency, load_demo_dataset
from app.api.v1.audit import _AUDIT_LOGS
from app.api.v1.objections import list_open_objects_for_ulpin

router = APIRouter(prefix="/integrity", tags=["Property Integrity Scores, Duplicate Sweep & Change Timeline"])

_DATASET = load_demo_dataset()
_HERO_ULPIN = "12345678901234"

_LEGACY_ISSUES = {
    # synthetic reconcilable legacy survey discrepancies (demo dataset)
    "12345678901239": {"label": "Legacy survey area mismatch", "detail": "Recorded 940 m² vs calculated 1000 m² — reconcilable under ROR/Reg. 6."},
    "12345678901245": {"label": "Easement notation pending", "detail": "Right-of-way servitude recorded for drainage channel; encumbrance entry pending updates."},
}


def _change_factor_for(parcel: Dict[str, Any]) -> Dict[str, Any]:
    if parcel["ulpin"] != _HERO_ULPIN:
        return {
            "key": "vertical_monitoring",
            "label": "Vertical (LiDAR) monitoring",
            "status": "INFO",
            "weight": 0,
            "detail": "No vertical twin acquired for this parcel — ground cadastre only.",
        }
    e2 = _DATASET["epoch2_change"]
    pct = round(100 * e2["delta_height_m"] / 18.0, 1)
    return {
        "key": "vertical_monitoring",
        "label": "Vertical (LiDAR) monitoring",
        "status": "FAIL" if pct > 5 else "PASS",
        "weight": 30,
        "detail": (
            f"Epoch-2 survey detects +{e2['delta_height_m']} m height delta "
            f"(18.0 → {e2['new_height_m']} m, {pct}%) and +1 floor — flagged as "
            "suspected unauthorized vertical growth."
        ),
    }


def _objection_factor_for(ulpin: str) -> Dict[str, Any]:
    open_obj = [o for o in list_open_objects_for_ulpin(ulpin)]
    if open_obj:
        return {
            "key": "open_objections",
            "label": "Open citizen objections",
            "status": "WARN",
            "weight": 10 * len(open_obj),
            "detail": f"{len(open_obj)} open objection(s) attached to this parcel.",
        }
    return {
        "key": "open_objections",
        "label": "Open citizen objections",
        "status": "PASS",
        "weight": 0,
        "detail": "No open objections.",
    }


def _evidence_factor(parcel: Dict[str, Any]) -> Dict[str, Any]:
    if parcel["ulpin"] == _HERO_ULPIN:
        return {
            "key": "evidence_coverage",
            "label": "Evidence coverage",
            "status": "PASS",
            "weight": 0,
            "detail": "6 evidence streams attached (LiDAR, imagery, deeds, chainage, FSI, UXO).",
        }
    return {
        "key": "evidence_coverage",
        "label": "Evidence coverage",
        "status": "WARN",
        "weight": 5,
        "detail": "No field evidence bound to parcel record.",
    }


def _validation_factor(parcel: Dict[str, Any]) -> Dict[str, Any]:
    if parcel["ulpin"] != _HERO_ULPIN:
        return {
            "key": "validation",
            "label": "Topology validation (R001–R016)",
            "status": "INFO",
            "weight": 0,
            "detail": "No rule-by-rule verdict is recorded against this parcel.",
        }
    return {
        "key": "validation",
        "label": "Topology validation (R001–R016)",
        "status": "WARN",
        "weight": 5,
        # This used to read "11/12 rules passed; R009 subsurface clash open",
        # which is a compliance verdict about a named parcel and a named
        # clash. Nothing computes it, and the rule count had already moved to
        # 16. The score now reports that no run is recorded rather than
        # inventing one.
        "detail": "No rule run is recorded for this parcel, so no pass count or clash list is claimed.",
    }


def _verification_factor(parcel: Dict[str, Any]) -> Dict[str, Any]:
    if parcel["ulpin"] == _HERO_ULPIN:
        return {
            "key": "verification",
            "label": "Cryptographic proof",
            "status": "WARN",
            "weight": 10,
            "detail": (
                "No independent verification exists. The record carries a "
                "self-signature made by this service with a published key, "
                "which shows the bytes are unaltered but not that any "
                "authority reviewed them."
            ),
        }
    return {
        "key": "verification",
        "label": "Cryptographic proof",
        "status": "WARN",
        "weight": 10,
        "detail": "No independent verification exists for this record.",
    }


def _concordance_factor(parcel: Dict[str, Any]) -> Dict[str, Any]:
    doc = parcel.get("document_area_m2") or 0
    calc = parcel.get("calculated_area_m2") or 0
    if doc <= 0:
        return {"key": "concordance", "label": "Cadastral area concordance", "status": "PASS", "weight": 0, "detail": "n/a"}
    pct = round(100 * abs(calc - doc) / doc, 1)
    if pct <= 1:
        return {
            "key": "concordance",
            "label": "Cadastral area concordance",
            "status": "PASS",
            "weight": 0,
            "detail": f"GIS area {calc:,.0f} m² matches record {doc:,.0f} m² (Δ{pct}%).",
        }
    return {
        "key": "concordance",
        "label": "Cadastral area concordance",
        "status": "WARN",
        "weight": 10,
        "detail": f"GIS area {calc:,.0f} m² vs recorded {doc:,.0f} m² diverges by Δ{pct}%.",
    }


def _duplicate_flags_for(ulpin: str) -> List[Dict[str, Any]]:
    flags: List[Dict[str, Any]] = []
    if ulpin == _HERO_ULPIN:
        ids = [u.get("proposed_3d_id") for u in _DATASET["units"]]
        if len(ids) != len(set(ids)):
            flags.append({"key": "unit_3d_id_collision", "severity": "HIGH", "message": "Duplicate proposed 3D-ID across strata units."})
    ls = _LEGACY_ISSUES.get(ulpin)
    if ls:
        flags.append({"key": "legacy_reconcile", "severity": "MEDIUM", "message": ls["label"] + " — " + ls["detail"]})
    return flags


def _score_for(parcel: Dict[str, Any]) -> Dict[str, Any]:
    ulpin = parcel["ulpin"]
    factors = [
        _concordance_factor(parcel),
        _change_factor_for(parcel),
        _evidence_factor(parcel),
        _validation_factor(parcel),
        _verification_factor(parcel),
        _objection_factor_for(ulpin),
    ]
    score = 100
    for f in factors:
        score -= f["weight"]
    flags = _duplicate_flags_for(ulpin)
    for fl in flags:
        if fl["severity"] == "MEDIUM":
            score -= 10
    score = max(0, min(100, score))
    band = "GREEN" if score >= 80 else "AMBER" if score >= 60 else "RED"
    top = max(factors, key=lambda f: f["weight"])
    return {
        "ulpin": ulpin,
        "survey_number": parcel["survey_number"],
        "has_3d_twin": ulpin == _HERO_ULPIN,
        "score": score,
        "band": band,
        "band_label": {"GREEN": "Healthy record", "AMBER": "Review recommended", "RED": "Requires investigation"}[band],
        "summary": top["detail"] if top["weight"] else "No material risk factors detected.",
        "factors": factors,
        "duplicate_flags": _duplicate_flags_for(ulpin),
    }


@router.get("/overview")
def integrity_overview(_guard: None = Depends(demo_mode_dependency)):
    """Compact integrity board over the full Airoli Sector 8 demo precinct."""
    parcels: List[Dict[str, Any]] = [_DATASET["hero_parcel"], *_DATASET["surrounding_parcels"]]
    rows = [_score_for(p) for p in parcels]
    bands = {"GREEN": 0, "AMBER": 0, "RED": 0}
    for r in rows:
        bands[r["band"]] += 1
    top_flags = []
    for r in rows:
        for f in r["duplicate_flags"]:
            if f["severity"] == "HIGH":
                top_flags.append({"ulpin": r["ulpin"], **f})
    return {
        "total_parcels": len(rows),
        "twin_parcels": 1,
        "bands": bands,
        "average_score": round(sum(r["score"] for r in rows) / len(rows), 1),
        "parcels": rows,
        "critical_flags": top_flags,
        "duplicate_sweep_summary": _duplicate_sweep()["summary"],
    }


@router.get("/duplicates")
def duplicate_sweep(_guard: None = Depends(demo_mode_dependency)):
    """Deterministic duplicate / collision sweep across the demo precinct."""
    return _duplicate_sweep()


def _duplicate_sweep() -> Dict[str, Any]:
    parcels: List[Dict[str, Any]] = [_DATASET["hero_parcel"], *_DATASET["surrounding_parcels"]]
    ulpins = [p["ulpin"] for p in parcels]
    survey = [p["survey_number"] for p in parcels]
    findings = []

    # 1. ULPIN format + uniqueness (14-char alphanumeric national identifier)
    for p in parcels:
        ulpin = p["ulpin"]
        if len(ulpin) != 14 or not ulpin.isalnum():
            findings.append({"severity": "HIGH", "kind": "ULPIN format failure", "ulpin": ulpin, "message": "ULPIN must be exactly 14 alphanumeric characters."})

    # 2. survey-number collisions
    dup_surveys = {s for s in survey if survey.count(s) > 1}
    for p in parcels:
        if p["survey_number"] in dup_surveys:
            findings.append({"severity": "HIGH", "kind": "Survey-number collision", "ulpin": p["ulpin"], "message": f"Survey number {p['survey_number']} reused across records."})

    # 3. duplicate ULPIN (should be impossible)
    if len(set(ulpins)) != len(ulpins):
        findings.append({"severity": "CRITICAL", "kind": "Duplicate ULPIN", "ulpin": "", "message": "Two records share the same ULPIN."})

    # 4. soft flags from legacy issues
    for ulpin, iss in _LEGACY_ISSUES.items():
        findings.append({"severity": "MEDIUM", "kind": "Reconciliation pending", "ulpin": ulpin, "message": iss["label"] + " — " + iss["detail"]})

    # 5. strata 3D-ID uniqueness (hero)
    ids = [u.get("proposed_3d_id") for u in _DATASET["units"]]
    if len(ids) != len(set(ids)):
        findings.append({"severity": "HIGH", "kind": "3D-ID collision", "ulpin": _HERO_ULPIN, "message": "Duplicate proposed 3D-ID in strata units."})

    return {
        "sweep_id": "DUP-SWEEP-2026-SEC08",
        "parcels_scanned": len(parcels),
        "units_scanned": len(_DATASET["units"]),
        "checks_run": ["ULPIN format (14-char)", "Survey-number uniqueness", "ULPIN uniqueness", "Strata 3D-ID uniqueness", "Legacy reconciliation"],
        "findings": findings,
        "summary": {
            "status": "NO_CRITICAL_DUPLICATES" if not any(f["severity"] in ("CRITICAL", "HIGH") for f in findings) else "ACTION_REQUIRED",
            "high_or_critical": sum(1 for f in findings if f["severity"] in ("CRITICAL", "HIGH")),
            "medium": sum(1 for f in findings if f["severity"] == "MEDIUM"),
            # Derived, not a remembered constant. This used to read "All 12
            # ULPINs" while the endpoint above reports whatever the dataset
            # actually holds, and it told the reader the items were "flagged for
            # department follow-up" as though some department had been notified.
            "notes": (
                f"{len(ulpins)} ULPIN(s) checked for format and uniqueness; "
                f"{len(ids)} strata 3D-ID(s) checked. "
                + (
                    f"{len(_LEGACY_ISSUES)} reconciliation item(s) are recorded in "
                    "this repo. They have not been sent to, reviewed by or "
                    "acknowledged by any department."
                    if _LEGACY_ISSUES
                    else "No reconciliation items are recorded."
                )
            ),
        },
    }


def _timeline_for(ulpin: str) -> List[Dict[str, Any]]:
    tl: List[Dict[str, Any]] = []
    found = next((p for p in [_DATASET["hero_parcel"], *_DATASET["surrounding_parcels"]] if p["ulpin"] == ulpin), None)
    if not found:
        return tl
    tl.append({
        "date": None,
        "kind": "survey",
        "title": f"No survey record on file for {found['survey_number']}",
        "detail": (
            "This parcel has never been surveyed. The previous entry dated this "
            "2025-11-18 and described it as a mutation of a legacy record under "
            "the Maharashtra Land Revenue Code; both the date and the statutory "
            "characterisation were invented."
        ),
    })
    for ev in _AUDIT_LOGS:
        ent = (ev.get("entity_id") or "")[:14]
        if ent == ulpin or (ulpin == _HERO_ULPIN and (ev["entity_type"] in ("JOB", "VALIDATION", "CASE") or "B17" in ev.get("entity_id", ""))):
            tl.append({
                "date": (ev.get("timestamp") or "")[:10],
                "kind": ev["event_type"].lower().replace("_", "-"),
                "title": ev["event_type"].replace("_", " ").title(),
                "detail": (ev.get("payload") or {}).get("action") or _json_dump_brief(ev.get("payload")),
            })
    if ulpin == _HERO_ULPIN:
        e2 = _DATASET["epoch2_change"]
        tl.append({
            "date": None,
            "kind": "monitoring",
            "title": "Epoch-2 change (synthetic, not a survey)",
            "detail": f"+{e2['delta_height_m']} m / +{e2['delta_floors']} floor detected — {e2['epoch_to']}.",
        })
    # Undated entries first, then chronological. Sorting the raw values raises
    # TypeError once any entry has date=None alongside the ISO-date strings.
    tl.sort(key=lambda e: (e["date"] is None, e["date"] or ""))
    return tl


def _json_dump_brief(payload: Any) -> str:
    if not isinstance(payload, dict):
        return str(payload)
    return "; ".join(f"{k}: {v}" for k, v in list(payload.items())[:3])


@router.get("/properties/{ulpin}")
def integrity_for_property(ulpin: str, _guard: None = Depends(demo_mode_dependency)):
    """Detailed integrity report, change timeline and building economics for one property."""
    parcels: List[Dict[str, Any]] = [_DATASET["hero_parcel"], *_DATASET["surrounding_parcels"]]
    parcel = next((p for p in parcels if p["ulpin"] == ulpin), None)
    if not parcel:
        raise HTTPException(status_code=404, detail="Unknown parcel ULPIN")
    report = _score_for(parcel)
    report["timeline"] = _timeline_for(ulpin)
    if ulpin == _HERO_ULPIN:
        struct = _DATASET["hero_structure"]
        e2 = _DATASET["epoch2_change"]
        roof_area = alt_roof_area(struct)
        fsi = struct["calculated_fsi"]
        report["building_economics"] = {
            "building_code": struct["building_code"],
            "floors_above_ground": struct["floors_count"],
            "basements": struct["basements_count"],
            "footprint_area_m2": roof_area,
            "total_built_up_area_m2": struct["total_built_up_area_m2"],
            "plot_area_m2": _DATASET["hero_parcel"]["document_area_m2"],
            "calculated_fsi": fsi,
            "max_allowed_fsi": _DATASET["precinct"]["max_allowed_fsi"],
            "fsi_utilization_pct": round(100 * fsi / _DATASET["precinct"]["max_allowed_fsi"], 1),
            "roof_catchment_elevation_m": e2["new_height_m"],
            "baseline_height_m": struct["height_m"],
            "detected_delta_height_m": e2["delta_height_m"],
            "detected_extra_floors": e2["delta_floors"],
        }
    return report


def alt_roof_area(struct: Dict[str, Any]) -> float:
    shape = struct["footprint_geojson"]["coordinates"][0]
    shoelace = 0.0
    for i in range(len(shape) - 1):
        x1, y1 = shape[i]
        x2, y2 = shape[i + 1]
        shoelace += x1 * y2 - x2 * y1
    return round(abs(shoelace) / 2.0, 2)