from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.security import get_current_user_payload, require_roles, TokenPayload, RoleEnum
from app.core.crypto import SigningKeyNotConfigured, sign_canonical_record
from app.core.crypto_disclosure import (
    CRYPTO_DISCLOSURE,
    NO_SIGNING_AUTHORITY,
    SIGNATURE_STATUS,
)
from app.core.audit_anchor import seal_chain_head, verify_against_checkpoints
from app.core.audit_chain import append_audit_event, list_events_for_entity, verify_full_chain
from app.core.hash_chain import GENESIS_HASH
from app.core.database import get_db
from app.models.audit import AuditEvent

router = APIRouter(prefix="/verification", tags=["Authority Verification Workflow"])

# In-memory cases store for live demo interaction
_CASES_DB = [
    {
        "id": "case-b17-001",
        "case_number": "CASE-2026-B17-001",
        "parcel_ulpin": "12345678901234",
        "structure_code": "B-17",
        "property_name": "Shree Ganesh CHS (Building B-17)",
        "case_type": "NEW_PROPERTY_REGISTRATION",
        "status": "NEEDS_REVIEW",
        "priority": "HIGH",
        "assigned_verifier": "Sunita Patil (Thane District Verifier)",
        "submitted_by": "Apex InfraProjects Ltd (Builder)",
        "created_at": "2026-09-24T10:15:00Z",
        "discrepancies_count": 1,
        "clash_summary": "1 Critical Subsurface Clash (PIPE-DRAIN-01 at Z=-3.2m)",
        "officer_notes": None,
        "correction_details": None,
        "decision_timestamp": None,
        "proposed_id": "12345678901234/B17-G-001-X",
    },
    {
        "id": "case-b17-002",
        "case_number": "CASE-2026-B17-002",
        "parcel_ulpin": "12345678901234",
        "structure_code": "B-17",
        "property_name": "Shree Ganesh CHS (Building B-17)",
        "case_type": "SUSPECTED_UNAUTHORIZED_CHANGE",
        "status": "NEEDS_REVIEW",
        "priority": "CRITICAL",
        "assigned_verifier": "Sunita Patil (Thane District Verifier)",
        "submitted_by": "Automated Multi-Epoch UAV Surveillance",
        "created_at": "2026-09-24T14:30:00Z",
        "discrepancies_count": 2,
        "clash_summary": "Detected +3.5m Height & Added 6th Floor Level (Units 601-604)",
        "officer_notes": None,
        "correction_details": None,
        "decision_timestamp": None,
        "proposed_id": "12345678901234/UB17-L05-601-Y",
    },
]


class ActionDecisionReq(BaseModel):
    decision: str  # APPROVE, REJECT, CORRECTION_REQUESTED
    officer_notes: str
    correction_details: Optional[str] = None


@router.get("/cases")
def list_verification_cases(
    status: Optional[str] = None,
    current_user: TokenPayload = Depends(get_current_user_payload),
):
    """Lists verification cases in the verifier's jurisdiction queue."""
    if status:
        return [c for c in _CASES_DB if c["status"] == status]
    return _CASES_DB


@router.get("/cases/{case_id}")
def get_case_details(case_id: str):
    """Retrieves a specific verification case by ID or by its case number.

    The list endpoint exposes both ``id`` ("case-b17-001") and the human-facing
    ``case_number`` ("CASE-2026-B17-001"), and the case number is what gets
    displayed and copied. Matching on id alone meant the identifier the UI
    shows 404'd when pasted back into this path.
    """
    for c in _CASES_DB:
        if case_id in (c["id"], c.get("case_number")):
            return c
    raise HTTPException(status_code=404, detail="Verification case not found.")


@router.post("/cases/{case_id}/decide")
async def decide_verification_case(
    case_id: str,
    req: ActionDecisionReq,
    db: AsyncSession = Depends(get_db),
    _auth: TokenPayload = Depends(require_roles([RoleEnum.TALUKA_VERIFIER, RoleEnum.DISTRICT_VERIFIER, RoleEnum.STATE_ADMIN])),
):
    """
    Authorized officer approves, rejects, or requests correction on a cadastral case.

    The decision is appended to the persisted hash chain in ``audit_events`` and
    committed before the response is returned. Previously this mutated an
    in-memory list and returned a signature, so an approval produced no durable
    record and the public QR proof had nothing to verify against.
    """
    target_case = None
    for c in _CASES_DB:
        # Accept the case number as well as the internal id, for the same
        # reason the read path does: the displayed identifier must work.
        if case_id in (c["id"], c.get("case_number")):
            target_case = c
            break

    if not target_case:
        raise HTTPException(status_code=404, detail="Verification case not found.")

    dec = req.decision.upper().strip()
    if dec in ("APPROVE", "APPROVED"):
        dec = "APPROVE"
    elif dec in ("REJECT", "REJECTED"):
        dec = "REJECT"
    elif dec in ("CORRECTION_REQUESTED", "REQUEST_MORE_INFO", "MORE_INFO"):
        dec = "CORRECTION_REQUESTED"
    else:
        raise HTTPException(status_code=400, detail="Decision must be APPROVE, REJECT, or CORRECTION_REQUESTED.")

    now_iso = datetime.now(timezone.utc).isoformat()
    target_case["status"] = "APPROVED" if dec == "APPROVE" else ("REJECTED" if dec == "REJECT" else "CORRECTION_REQUESTED")
    target_case["officer_notes"] = req.officer_notes
    target_case["correction_details"] = req.correction_details
    target_case["decision_timestamp"] = now_iso

    # If approved, generate digital signature and record cryptographic proof
    sig_info = None
    signing_note = None
    if dec == "APPROVE":
        canonical_payload = {
            "case_number": target_case["case_number"],
            "parcel_ulpin": target_case["parcel_ulpin"],
            "structure_code": target_case["structure_code"],
            "decision": "APPROVED",
            "officer": _auth.sub or "District Verifier",
            "timestamp": now_iso,
        }
        # A missing Ed25519 key must not block the decision. Before this was
        # caught, an unconfigured deployment 500'd on every approval and the
        # audit record was lost with it, so the one step that cannot silently
        # fail was the one that failed hardest. The hash chain still links the
        # decision; only the signature is absent, and it says so.
        try:
            fp, sig = sign_canonical_record(canonical_payload)
        except SigningKeyNotConfigured as exc:
            fp, sig = None, None
            signing_note = str(exc)

        sig_info = {
            "fingerprint_sha256": fp,
            "digital_signature_ed25519": sig,
            "signed": sig is not None,
            "signing_note": signing_note,
            # The case was approved by whoever called this endpoint, recorded
            # as target_case["officer_notes"] and the authenticated subject
            # above. That decision is not a land-records signature, and no
            # Thane District verifier signed anything.
            "signer_authority": NO_SIGNING_AUTHORITY,
            "status": SIGNATURE_STATUS,
            "disclosure": CRYPTO_DISCLOSURE,
        }

    # Persist the decision to the tamper-evident chain. This is the step the PS
    # lifecycle turns on: approve -> record -> public proof. It happens before
    # the response so a 200 always means the record is durable.
    event_type = f"CASE_{target_case['status']}"
    audit_event = await append_audit_event(
        db,
        event_type=event_type,
        entity_type="CASE",
        entity_id=target_case["id"],
        actor_id=_auth.sub or "unknown_officer",
        timestamp_iso=now_iso,
        payload={
            "case_number": target_case["case_number"],
            "parcel_ulpin": target_case["parcel_ulpin"],
            "structure_code": target_case["structure_code"],
            "proposed_id": target_case.get("proposed_id"),
            "decision": target_case["status"],
            "officer_notes": req.officer_notes,
            "correction_details": req.correction_details,
            "fingerprint_sha256": (sig_info or {}).get("fingerprint_sha256"),
            "signer_authority": (sig_info or {}).get("signer_authority", NO_SIGNING_AUTHORITY),
        },
    )

    return {
        "message": f"Case {target_case['case_number']} successfully transitioned to {target_case['status']}.",
        "case": target_case,
        "cryptographic_proof": sig_info,
        "audit_record": {
            "event_number": audit_event.event_number,
            "event_id": audit_event.id,
            "previous_hash": audit_event.previous_hash,
            "current_hash": audit_event.current_hash,
            "actor_id": audit_event.actor_id,
            "timestamp": audit_event.timestamp.isoformat() if audit_event.timestamp else now_iso,
            "persisted": True,
        },
        "signature_status": (
            "signed"
            if (sig_info or {}).get("signed")
            else "unsigned: no Ed25519 key configured. The decision is still "
            "recorded in the tamper-evident chain; it is not cryptographically "
            "signed by an officer."
        ),
    }


@router.get("/chain/verify")
async def verify_audit_chain(db: AsyncSession = Depends(get_db)):
    """Recompute the whole audit chain from genesis and report any break.

    Public by design: the property statement's value depends on a member of the
    public being able to check that an approved record was not altered. The
    response carries no officer identity, no notes and no parcel geometry, only
    hashes and counts, so it discloses nothing under DPDP.
    """
    result = await verify_full_chain(db)
    anchor = await verify_against_checkpoints(db)
    return {
        "algorithm": "SHA-256 chained: H_n = SHA256(H_{n-1} || canonical(event))",
        "note": (
            "Tamper-evident audit log, not a distributed ledger. There is no peer "
            "network and no consensus."
        ),
        "chain": result,
        # Reported separately because a rehashed forgery passes the chain check
        # and is only caught here. Collapsing these into one boolean would hide
        # exactly the case that matters.
        "external_anchor": anchor,
        "valid": bool(result["valid"]) and anchor.get("matches_checkpoint") is not None,
        "what_this_proves": (
            "chain_valid proves no event was altered in place. anchored proves the "
            "head still matches an Ed25519-signed checkpoint held outside the chain, "
            "which is what detects a forgery that recomputed its own hashes. Neither "
            "is a distributed ledger and neither survives a compromised signing key."
        ),
    }


@router.post("/chain/checkpoint")
async def seal_chain_checkpoint(
    db: AsyncSession = Depends(get_db),
    _auth: TokenPayload = Depends(require_roles([RoleEnum.DISTRICT_VERIFIER, RoleEnum.STATE_ADMIN])),
):
    """Sign the current chain head so later rewrites become detectable.

    Without a sealed checkpoint, anyone able to UPDATE ``audit_events`` can
    rewrite history and rehash it so every entry verifies. Sealing is what makes
    the difference between "no one edited a row" and "no one can edit history
    without leaving evidence".
    """
    from app.core.audit_chain import get_chain_head

    head = await get_chain_head(db)
    result = await verify_full_chain(db)
    checkpoint = await seal_chain_head(
        db,
        head_hash=head["current_hash"],
        head_event_number=head["event_number"],
        event_count=result["event_count"],
        note=f"sealed after chain verification (chain_valid={result['valid']})",
    )
    return {"checkpoint": checkpoint, "chain_valid_at_seal": result["valid"]}


@router.get("/chain/checkpoints")
async def list_checkpoints(db: AsyncSession = Depends(get_db)):
    """Every sealed checkpoint with its signature status. Public, hashes only."""
    from sqlalchemy import select

    from app.core.audit_anchor import verify_checkpoint_signature
    from app.models.audit import AuditCheckpoint

    rows = await db.execute(select(AuditCheckpoint).order_by(AuditCheckpoint.checkpoint_number.asc()))
    out = []
    for cp in rows.scalars().all():
        sig = await verify_checkpoint_signature(cp)
        out.append({
            "checkpoint_number": cp.checkpoint_number,
            "head_hash": cp.head_hash,
            "head_event_number": cp.head_event_number,
            "event_count": cp.event_count,
            "algorithm": cp.algorithm,
            "signature_valid": sig.get("signature_valid"),
            "signature_note": sig.get("reason"),
            "created_at": cp.created_at.isoformat() if cp.created_at else None,
            "note": cp.note,
        })
    return {"count": len(out), "checkpoints": out, "genesis_hash": GENESIS_HASH}


@router.get("/cases/{case_id}/audit")
async def get_case_audit_trail(case_id: str, db: AsyncSession = Depends(get_db)):
    """Every persisted audit event for one case, oldest first."""
    target = next(
        (c for c in _CASES_DB if case_id in (c["id"], c.get("case_number"))), None
    )
    if not target:
        raise HTTPException(status_code=404, detail="Verification case not found.")

    events = await list_events_for_entity(db, target["id"])
    return {
        "case_number": target["case_number"],
        "case_id": target["id"],
        "event_count": len(events),
        "events": [
            {
                "event_number": e.event_number,
                "event_type": e.event_type,
                "actor_id": e.actor_id,
                "previous_hash": e.previous_hash,
                "current_hash": e.current_hash,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "payload": e.payload,
            }
            for e in events
        ],
    }
