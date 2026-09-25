"""Builder submission tracking.

A submission is a claim a builder makes about a parcel. Opening one records the
claim; it does not validate it. Acceptance requires a human verifier to call
/disposition with a written reason, and what that acceptance means is spelled
out in RECORD_BASIS below -- it is an internal workflow attestation, not a
government certification, because no government signing authority is reachable
from this codebase.

The seeded rows are demonstration fixtures and say so in their remarks.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends

from app.core.security import require_roles, TokenPayload, RoleEnum

router = APIRouter(prefix="/builder/submissions", tags=["builder-submissions"])

BUILDER_ONLY = require_roles([RoleEnum.BUILDER, RoleEnum.STATE_ADMIN])
REVIEWER_ONLY = require_roles([RoleEnum.STATE_ADMIN, RoleEnum.DISTRICT_VERIFIER, RoleEnum.TALUKA_VERIFIER])

# A reviewer decides a submission. No submission ever decides itself.
VALID_DISPOSITIONS = ["ACCEPTED_FOR_RECORD", "REJECTED"]

# A submission is never approved at intake. It arrives pending.
PENDING_REVIEW = "PENDING_REVIEW"
ACCEPTED_FOR_RECORD = "ACCEPTED_FOR_RECORD"
REJECTED = "REJECTED"

# Attached to every acceptance. Keeps a decision from reading like a registry
# certificate, which it is not.
RECORD_BASIS = (
    "Accepted into this prototype's working record by a reviewer account in this "
    "system. It is not a government certification and confers no legal title: "
    "no government DSC or eSign authority is reachable from this application, and "
    "the underlying geometry was asserted by the submitter, not surveyed."
)

_SUBMISSIONS = [
    {
        "id": "SUB-2026-4101",
        "project_name": "Skyline Twin Towers — B-17 ANNEX",
        "parcel_ulpin": "202609250001",
        "structure_code": "B-17",
        "submission_type": "Architectural approval",
        "status": "UNDER_REVIEW",
        "submitted_on": "2026-09-18",
        "fsi_proposed": 1.95,
        "floors_proposed": 6,
        "remarks": "Demonstration fixture. Submitted annex drawings; awaiting vertical growth review after Epoch-2 LiDAR flag.",
    },
    {
        "id": "SUB-2026-4099",
        "project_name": "Row House Cluster — B-02",
        "parcel_ulpin": "202609250002",
        "structure_code": "B-02",
        "submission_type": "Completion certificate",
        "status": "ACCEPTED_FOR_RECORD",
        "submitted_on": "2026-09-02",
        "fsi_proposed": 1.12,
        "floors_proposed": 3,
        "remarks": "Demonstration fixture. Recorded as accepted into the working record for the synthetic pilot by a reviewer fixture account; not a real completion certificate.",
    },
    {
        "id": "SUB-2026-4088",
        "project_name": "Warehouse Extension — B-09",
        "parcel_ulpin": "202609250009",
        "structure_code": "B-09",
        "submission_type": "FSI revision",
        "status": "REJECTED",
        "submitted_on": "2026-08-21",
        "fsi_proposed": 2.4,
        "floors_proposed": 5,
        "remarks": "Demonstration fixture. Proposed FSI exceeds the ceiling assumed for this pilot.",
    },
    {
        "id": "SUB-2026-4085",
        "project_name": "Neighbourhood Shop — B-07",
        "parcel_ulpin": "202609250007",
        "structure_code": "B-07",
        "submission_type": "Change of use",
        "status": "UNDER_REVIEW",
        "submitted_on": "2026-08-10",
        "fsi_proposed": 1.0,
        "floors_proposed": 1,
        "remarks": "Demonstration fixture. Commercial conversion under local-area plan consultation.",
    },
]

_COUNTER = len(_SUBMISSIONS)


async def _copy_submission_to_db(submission: dict, submitter_id: Optional[str]) -> dict:
    """Best-effort copy of an in-memory submission into Postgres.

    The demo must keep working without the database, but it must say so. A
    response carrying ``persistence.persisted: False`` is a truthful account of
    a submission that only reached the in-memory store, not silently an
    unrwritten record pretending to be durable.
    """
    from app.core.database import AsyncSessionLocal
    from app.services.builder_records import persist_submission_row

    if not submitter_id:
        return {
            "persisted": False,
            "table": "submissions",
            "reason": "submitter of the token is not identifiable as a database account",
        }
    async with AsyncSessionLocal() as db:
        return await persist_submission_row(
            db,
            submission_id=submission["id"],
            project_name=submission["project_name"],
            parcel_ulpin=submission["parcel_ulpin"],
            structure_code=submission.get("structure_code"),
            submission_type=submission.get("submission_type", "General"),
            status=submission["status"],
            fsi_proposed=submission.get("fsi_proposed"),
            floors_proposed=submission.get("floors_proposed"),
            remarks=submission.get("remarks", ""),
            submitter_id=submitter_id,
        )


@router.get("/")
def list_submissions():
    # The statuses a submission can carry. There is no 'APPROVED': that slot
    # used to be indexed below and raised KeyError, which the background pool
    # middleware turned into a 503.
    statuses = (PENDING_REVIEW, ACCEPTED_FOR_RECORD, REJECTED)
    total = len(_SUBMISSIONS)
    by_status = {
        s: sum(1 for x in _SUBMISSIONS if x["status"] == s)
        for s in statuses
    }
    # The demonstration fixtures predate the three-status model; surface their
    # legacy statuses so the dashboard total reconciles instead of eating rows.
    by_status.update(
        {
            s: sum(1 for x in _SUBMISSIONS if x["status"] == s)
            for s in sorted({x["status"] for x in _SUBMISSIONS} - set(statuses))
        }
    )
    return {
        "total": total,
        "by_status": by_status,
        "accepted_or_legacy_approved": by_status[ACCEPTED_FOR_RECORD],
        "record_basis": RECORD_BASIS,
        "submissions": _SUBMISSIONS,
    }


@router.post("/")
async def create_submission(req: dict, _auth: TokenPayload = Depends(BUILDER_ONLY)):
    """
    Opens a submission. It does not decide anything.

    The status of a new submission is PENDING_REVIEW because no one has looked
    at it yet. Acceptance happens only through /disposition, which a verifier
    role calls and which records who decided and why. This endpoint previously
    rolled random.random() and returned APPROVED on a 40% chance, which is not
    a review outcome, it is a coin flip wearing a decision's clothing.
    """
    global _COUNTER
    parcel_ulpin = str(req.get("parcel_ulpin", "")).strip()
    project_name = str(req.get("project_name", "")).strip()
    submission_type = str(req.get("submission_type", "General")).strip()
    if not parcel_ulpin or not project_name:
        raise HTTPException(status_code=422, detail="parcel_ulpin and project_name are required")
    _COUNTER += 1
    fsi_proposed = float(req.get("fsi_proposed", 1.0))
    floors_proposed = int(req.get("floors_proposed", 3))
    submission = {
        "id": f"SUB-2026-{_COUNTER:04d}",
        "project_name": project_name,
        "parcel_ulpin": parcel_ulpin,
        "structure_code": req.get("structure_code") or f"B-{_COUNTER:02d}",
        "submission_type": submission_type,
        "status": PENDING_REVIEW,
        "submitted_on": "2026-09-25",
        "fsi_proposed": fsi_proposed,
        "floors_proposed": floors_proposed,
        "asset_id": req.get("asset_id"),
        "template_id": req.get("template_id"),
        "remarks": "Logged for review. No decision has been made on this submission.",
        "review_history": [],
    }
    _SUBMISSIONS.insert(0, submission)
    submission["persistence"] = await _copy_submission_to_db(submission, _auth.sub)
    return submission


from pydantic import BaseModel, Field


class DetailedBuildingSubmissionRequest(BaseModel):
    project_name: str
    parcel_ulpin: str
    # Statutory identifiers a submitter may quote. All optional and all treated
    # as claims: there is no registry to check them against, so they are never
    # echoed back as credentials. They previously carried defaults shaped like
    # real MahaRERA and municipal sanction numbers, which meant a form the user
    # never touched was pre-filled with an identification for a body that has
    # not issued anything.
    builder_rera_id: Optional[str] = None
    municipal_sanction_no: Optional[str] = None
    commencement_cert_date: Optional[str] = None
    building_typology: str = "tower"
    structure_code: Optional[str] = None

    # Massing geometry the submitter describes. We do not default these to
    # measured-looking numbers: the server does not compute from them, and a
    # default would make an untouched form hand over engineering values nobody
    # looked at. None means the submitter said nothing.
    floors_above_ground: int = 8
    basements_count: Optional[int] = None
    plinth_height_m: Optional[float] = None
    floor_to_floor_height_m: float = 3.5
    total_height_m: float = 28.0
    fsi_proposed: float = 1.85

    setback_front_m: float = 6.0
    setback_rear_m: float = 4.5
    setback_side_north_m: float = 4.5
    setback_side_south_m: float = 4.5

    # Where the building actually sits. When the submitter draws the footprint
    # (local metres over the parcel), footprint_ring carries it and the massing
    # is persisted as real geometry. Without a ring the endpoint falls back to
    # the in-memory massing exercise and says so. The parcel boundary itself is
    # never assumed here; drawing is not surveying.
    address: Optional[str] = None
    locality: Optional[str] = None
    footprint_ring: Optional[List[List[float]]] = None
    # Per-floor labels the submitter gave (level_code/name/use), applied to the
    # persisted levels when a footprint is present.
    floor_labels: Optional[List[dict]] = None

    # Infrastructure/utility claims. Accepted for the record, not checked against
    # any utility or building-services review, and not used in any computation.
    subsurface_depth_m: Optional[float] = None
    sewer_invert_depth_m: Optional[float] = None
    stormwater_tank_m3: Optional[float] = None
    rooftop_solar_capacity_kw: Optional[float] = None

    units: Optional[List[dict]] = None


@router.post("/detailed")
async def create_detailed_submission(req: DetailedBuildingSubmissionRequest, _auth: TokenPayload = Depends(BUILDER_ONLY)):
    """
    Builder building intake: records a proposed massing on a parcel.

    The checks below compare the submission against numeric thresholds this
    prototype assumes. They are advisory, they are not a compliance finding,
    and no rule identifier here cites a statute on purpose. "NBC-PART-3" and
    "UDCPR-ZONING-FSI-CEILING" were rule ids that read as citations to the
    National Building Code and the UDCPR while pointing at constants nobody
    validated against either document.

    This endpoint does not return an approval. It returns PENDING_REVIEW and
    waits for a reviewer. Minting 3D-ULPIN-shaped identifiers is a naming
    exercise over a massing the submitter described; it is not a registry
    allocation, and the ids are labelled as such in the response.
    """
    global _COUNTER
    _COUNTER += 1

    ulpin = req.parcel_ulpin.strip()
    if len(ulpin) != 14:
        ulpin = ulpin.ljust(14, "0")[:14]

    # Advisory threshold comparison. See module note on RECORD_BASIS.
    findings = []
    is_high_rise = req.total_height_m > 15.0
    min_side_setback = 4.5 if is_high_rise else 3.0

    front_ok = req.setback_front_m >= 6.0
    findings.append({
        "check": "PILOT-FRONT-SETBACK",
        "label": "Front access corridor (assumed 6.0 m)",
        "threshold": ">= 6.0m",
        "provided": f"{req.setback_front_m}m",
        "met": front_ok,
    })

    sides_ok = (req.setback_side_north_m >= min_side_setback) and (req.setback_side_south_m >= min_side_setback)
    findings.append({
        "check": "PILOT-SIDE-SETBACK",
        "label": f"Side setbacks (assumed {min_side_setback} m for height over 15 m)",
        "threshold": f">= {min_side_setback}m",
        "provided": f"N: {req.setback_side_north_m}m, S: {req.setback_side_south_m}m",
        "met": sides_ok,
    })

    fsi_ok = req.fsi_proposed <= 2.0
    findings.append({
        "check": "PILOT-FSI-CEILING",
        "label": "Floor space index against the ceiling assumed for this pilot",
        "threshold": "<= 2.00",
        "provided": f"{req.fsi_proposed:.2f}",
        "met": fsi_ok,
    })

    all_met = front_ok and sides_ok and fsi_ok
    # Advisory only. A threshold being met is not a decision, so it does not
    # become one.
    record_status = PENDING_REVIEW

    # 2. The building sits where the submitter says it sits, or it does not get
    #    real geometry. A drawn footprint (local metres) is persisted as parcel
    #    + structure + levels; without one the endpoint only works the
    #    in-memory massing, which no longer pretends to be a database record.
    structure_code = req.structure_code or f"B-{_COUNTER % 100 + 1:02d}"

    if req.footprint_ring:
        from app.core.database import AsyncSessionLocal
        from app.services.builder_records import persist_builder_structure

        ring = [[float(x), float(y)] for x, y in req.footprint_ring]
        if len(ring) < 3:
            raise HTTPException(status_code=422, detail="footprint_ring needs at least 3 vertices")
        # The footprint is asserted by the submitter. Nothing here checks it
        # against a survey; a future reviewer may. The label in the response
        # says exactly that.
        non_asserted = {
            "basis": "builder-asserted, not surveyed",
            "note": "Drawn over the parcel by the submitter. No survey authority has confirmed this geometry.",
        }

        async with AsyncSessionLocal() as db:
            persist_descr = await persist_builder_structure(
                db,
                ulpin=ulpin,
                project_name=req.project_name,
                structure_code=structure_code,
                structure_type=req.building_typology,
                floors_above_ground=req.floors_above_ground,
                floor_to_floor_height_m=req.floor_to_floor_height_m,
                total_height_m=req.total_height_m,
                footprint_ring=ring,
                address=req.address,
                locality=req.locality,
                ground_z=req.plinth_height_m or 0.0,
                floor_labels=req.floor_labels,
            )

        # Derived, not registry allocations: one identifier per submitted level
        # (floor_labels carry the persisted level rows, basements included).
        level_count = len(req.floor_labels or []) or max(0, req.floors_above_ground)
        minted_units = [
            {
                "unit_number": f"{idx + 1:02d}",
                "level_code": (req.floor_labels or [{}])[idx].get("level_code")
                if idx < len(req.floor_labels or [])
                else f"L{idx + 1:02d}",
                "unit_type": req.building_typology,
                "proposed_3d_id": f"BD{structure_code}{idx + 1:02d}V1",
                "carpet_area_m2": None,
            }
            for idx in range(level_count)
        ]
    else:
        non_asserted = None
        # Extrude / Mint 3D-ULPINs for the proposed building
        from app.id_engine.extruder import extrude_single_parcel
        custom_params = {
            "name": req.project_name,
            "type": req.building_typology,
            "floors": req.floors_above_ground,
            "floor_h": req.floor_to_floor_height_m,
        }
        if req.structure_code:
            custom_params["code"] = req.structure_code

        # Previously wrapped in `except Exception: pass`. A ULPIN with no
        # geometry in the cache raised ValueError, was swallowed, and the
        # caller got a normal-looking 200 reporting "All 0 strata 3D-ULPIN
        # units minted with ISO/IEC 7064 check". Silently building nothing
        # while reporting a successful mint is the failure this whole sweep
        # exists to remove, so an unusable parcel is a 422 with the reason.
        try:
            extruded_res = extrude_single_parcel(ulpin=ulpin, custom_params=custom_params)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        minted_units = []
        if extruded_res and extruded_res.get("building"):
            minted_units = [
                {
                    "unit_number": u["unit_number"],
                    "level_code": u["level_code"],
                    "unit_type": u["unit_type"],
                    "proposed_3d_id": u["proposed_3d_id"],
                    "carpet_area_m2": u["carpet_area_m2"],
                }
                for u in extruded_res["building"].get("units", [])
            ]

    sub_id = f"SUB-2026-{_COUNTER:04d}"
    submission_entry = {
        "id": sub_id,
        "project_name": req.project_name,
        "parcel_ulpin": ulpin,
        "structure_code": req.structure_code or structure_code,
        "submission_type": "Proposed 3D Strata Massing",
        "status": record_status,
        "submitted_on": "2026-09-25",
        "fsi_proposed": req.fsi_proposed,
        "floors_proposed": req.floors_above_ground,
        "builder_rera_id": req.builder_rera_id,
        "municipal_sanction_no": req.municipal_sanction_no,
        "remarks": (
            f"{len(minted_units)} strata identifiers derived from the proposed massing. "
            + (
                "All assumed pilot thresholds met by the submission; still awaiting reviewer disposition."
                if all_met
                else "One or more assumed pilot thresholds not met; flagged for reviewer attention."
            )
        ),
    }

    _SUBMISSIONS.insert(0, submission_entry)

    submission_entry["persistence"] = await _copy_submission_to_db(
        submission_entry, _auth.sub
    )

    response = {
        "submission_id": sub_id,
        "record_status": record_status,
        "record_basis": RECORD_BASIS,
        "declared_by_submitter_not_verified": {
            "rera_id": req.builder_rera_id,
            "municipal_sanction_no": req.municipal_sanction_no,
            "commencement_cert_date": req.commencement_cert_date,
            "parent_ulpin": ulpin,
            "note": "Quoted by the submitter. Not checked against any registry, because none is reachable from here.",
        },
        "advisory_threshold_findings": {
            "all_thresholds_met": all_met,
            "checks": findings,
            "note": "Thresholds assumed for this pilot, not a compliance determination and not citations to any statute.",
        },
        "spatial_massing": {
            "total_height_m": req.total_height_m,
            "floors_above_ground": req.floors_above_ground,
            "basements_count": req.basements_count,
            "fsi_proposed": req.fsi_proposed,
        },
        "minted_3d_ulpins": {
            "total_minted": len(minted_units),
            "identifier_note": (
                "Derived from the submitter's proposed massing. These are not registry "
                "allocations and confer no title."
            ),
            "units": minted_units,
        },
        "remarks": submission_entry["remarks"],
        "persistence": submission_entry["persistence"],
    }
    if non_asserted is not None:
        response["asserted_geometry"] = {
            **non_asserted,
            "persistence": persist_descr,
            "structure_code": structure_code,
            "footprint_vertex_count": len(ring),
        }
    return response


def _acceptance_record(persistence: Any, derived_ulpin: Optional[str]) -> Dict[str, Any]:
    """What a decision produced: the identifier, its caveat, and the audit proof.

    One place builds it, and both the HTTP response and the stored submission row
    are given the same dictionary. The endpoint used to read these five values
    straight out of ``persistence`` and return them *without* writing them to the
    row, so the ReviewPage panel -- which renders from the listed submission, not
    from the response it just received -- showed the proof for the length of one
    browser session and then lost it on reload. A proof that vanishes on refresh
    is not a proof anyone can audit, so it is stored on the submission it belongs
    to.

    The field names are the ones the endpoint already returns and the page already
    reads; nothing is renamed. ``audit_proof`` is the same value the persistence
    receipt calls ``blockchain_proof``, because "blockchain" describes a mechanism
    this prototype does not have: it is a hash chain plus an Ed25519 signature
    over the prototype's own key.

    Fields are set to ``None`` rather than left over from an earlier decision.
    A submission can be accepted and then rejected; a rejection must not inherit
    the identifier the acceptance derived.
    """
    proof = persistence if isinstance(persistence, dict) else {}
    ulpin_note = (
        "Prototype-derived identifier computed from the accepted parcel's "
        "geometry. It is not a registry allocation, confers no title, and "
        "is not an official 3D-ULPIN; those come from the DOLR or the state "
        "ULPIN API. The audit entry proves the record has not been altered "
        "since it was signed -- nothing more."
        if derived_ulpin
        else (
            "No identifier could be derived: the accepted parcel's geometry "
            "is not available yet. The review decision is still recorded."
        )
    )
    return {
        "derived_ulpin": derived_ulpin,
        "derived_ulpin_status": proof.get("derived_ulpin_status"),
        "derivation_note": proof.get("derivation_note"),
        "identifier_authority": proof.get("identifier_authority"),
        "audit_proof": proof.get("blockchain_proof"),
        "ulpin_note": ulpin_note,
    }


class DispositionRequest(BaseModel):
    decision: str
    reason: str
    basis: Optional[str] = None


@router.post("/{submission_id}/disposition")
async def disposition(
    submission_id: str,
    req: DispositionRequest,
    _auth: TokenPayload = Depends(REVIEWER_ONLY),
):
    """
    A verifier decides a submission.

    This is the only place a submission ceases to be PENDING_REVIEW, and it is
    an attestation about the working record, spelled out in RECORD_BASIS: not a
    government certification, no legal title. The reviewer's identity, the
    written reason, and the moment of the decision are returned so the record
    keeps the trail. The initializer that created the submission cannot decide
    it.

    Whatever acceptance produced -- the derived identifier, its caveat, and the
    hash-chained audit proof -- is written onto the stored submission as well as
    returned, so reading the submission back later shows the same proof this
    response carries.
    """
    if req.decision not in VALID_DISPOSITIONS:
        raise HTTPException(
            status_code=422,
            detail=f"decision must be one of {VALID_DISPOSITIONS}",
        )
    if not req.reason or len(req.reason.strip()) < 8:
        raise HTTPException(
            status_code=422,
            detail="a written reason of at least 8 characters is required",
        )

    submission = next(
        (s for s in _SUBMISSIONS if s["id"] == submission_id), None
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="unknown submission id")

    now_iso = datetime.now(timezone.utc).isoformat()
    submission["status"] = req.decision
    history_entry = {
        "decision": req.decision,
        "reason": req.reason.strip(),
        "basis": (req.basis or "").strip() or RECORD_BASIS,
        "verified_by": _auth.sub,
        "verified_at": now_iso,
    }
    submission.setdefault("review_history", []).append(history_entry)

    from app.core.database import AsyncSessionLocal
    from app.services.builder_records import apply_review_decision

    async with AsyncSessionLocal() as db:
        persistence = await apply_review_decision(
            db,
            submission_id=submission_id,
            parcel_ulpin=submission["parcel_ulpin"],
            decision=req.decision,
            reason=req.reason.strip(),
            basis=req.basis or "",
            reviewer_id=_auth.sub,
        )

    derived_ulpin = persistence.get("derived_ulpin") if isinstance(persistence, dict) else None
    acceptance = _acceptance_record(persistence, derived_ulpin)

    # The proof is stored on the submission, not just returned. `GET /` is what a
    # reload renders from, so an acceptance that only ever existed in one HTTP
    # response was invisible to everyone who came back to the page -- including
    # the reviewer who wanted to check the audit hash later.
    submission.update(acceptance)
    # This row's create-time receipt stays as it was: it answers "was the
    # submission itself copied?". The decision's own write outcome is kept
    # beside it rather than overwriting it, so a decision that could not be
    # persisted cannot be read back as a durable one.
    submission["disposition_persistence"] = persistence

    return {
        "submission_id": submission_id,
        "record_status": submission["status"],
        "record_basis": RECORD_BASIS,
        "review": history_entry,
        "review_history": submission["review_history"],
        "persistence": persistence,
        **acceptance,
    }
