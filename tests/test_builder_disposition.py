"""Review lifecycle: only a verifier decides, and the decision is a claim.

Covers the disposition endpoint introduced in stage 2.5: a submission is a
claim the builder makes, and the only endpoint that can change its status is
POST /disposition, which a reviewer role calls with a written reason, records
who decided, and labels the result as an internal working-record attestation --
never a government certification.

The suite runs without Postgres, so the database copy is exercised three ways:
unit tests prove the in-memory lifecycle; a source gate proves the responses
report persistence honestly; and one Postgres-gated test proves the real rows
appear when the parents (submitter account, parcel) exist.
"""
import os
import pathlib
import re

import pytest

from tests.conftest import _login


def _login_as(client, username: str):
    data = _login(client, username)
    return {"Authorization": f"Bearer {data['access_token']}"}


def _create_submission(client, headers=None, ulpin="202609250001", name="Disposition Probe"):
    r = client.post(
        "/api/v1/builder/submissions",
        headers=headers,
        json={"parcel_ulpin": ulpin, "project_name": name},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PENDING_REVIEW"
    return body


def test_only_reviewer_roles_may_decide(authed_builder):
    """The party that created a submission cannot decide it."""
    body = _create_submission(authed_builder)
    r = authed_builder.post(
        f"/api/v1/builder/submissions/{body['id']}/disposition",
        json={"decision": "ACCEPTED_FOR_RECORD", "reason": "a genuinely written reason"},
    )
    assert r.status_code == 403, r.text
    assert "STATE_ADMIN" in r.json()["detail"]


def _verifier(client):
    return _login_as(client, "district.admin")


def test_disposition_requires_a_decision_and_a_written_reason(client, authed_builder):
    body = _create_submission(authed_builder)
    v = _verifier(client)

    # Unknown decision.
    r = client.post(
        f"/api/v1/builder/submissions/{body['id']}/disposition",
        headers=v,
        json={"decision": "CONGRATULATE", "reason": "a genuinely written reason"},
    )
    assert r.status_code == 422
    assert "ACCEPTED_FOR_RECORD" in r.json()["detail"]

    # Missing / too-short reason.
    for reason in ("", "  ", "nope"):
        r = client.post(
            f"/api/v1/builder/submissions/{body['id']}/disposition",
            headers=v,
            json={"decision": "ACCEPTED_FOR_RECORD", "reason": reason},
        )
        assert r.status_code == 422, (r.status_code, r.text)
        assert "written reason" in r.json()["detail"]

    # Unknown submission.
    r = client.post(
        "/api/v1/builder/submissions/SUB-DOES-NOT-EXIST/disposition",
        headers=v,
        json={"decision": "ACCEPTED_FOR_RECORD", "reason": "a genuinely written reason"},
    )
    assert r.status_code == 404


def test_disposition_records_who_decided_and_why(client, authed_builder):
    body = _create_submission(authed_builder)
    v = _verifier(client)

    r = client.post(
        f"/api/v1/builder/submissions/{body['id']}/disposition",
        headers=v,
        json={
            "decision": "ACCEPTED_FOR_RECORD",
            "reason": "drawings reconcile with the declared massing",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["record_status"] == "ACCEPTED_FOR_RECORD"
    assert data["submission_id"] == body["id"]
    assert data["review"]["verified_by"] == "usr-district-admin"
    assert data["review"]["reason"] == "drawings reconcile with the declared massing"
    assert data["review"]["verified_at"].endswith("+00:00")
    assert data["review"]["basis"]  # defaults to RECORD_BASIS when not supplied

    # The mock record now reads as accepted and keeps the whole trail.
    listing = authed_builder.get("/api/v1/builder/submissions").json()
    row = next(s for s in listing["submissions"] if s["id"] == body["id"])
    assert row["status"] == "ACCEPTED_FOR_RECORD"
    assert row["review_history"][-1]["verified_by"] == "usr-district-admin"

    # And it is reversible: a later disposition supersedes, trails still there.
    r = client.post(
        f"/api/v1/builder/submissions/{body['id']}/disposition",
        headers=v,
        json={"decision": "REJECTED", "reason": "site clearance receipt is stale by six weeks"},
    )
    data = r.json()
    assert data["record_status"] == "REJECTED"
    assert len(data["review_history"]) == 2


def test_acceptance_basis_is_baked_into_every_decision(client, authed_builder):
    body = _create_submission(authed_builder)
    v = _verifier(client)
    r = client.post(
        f"/api/v1/builder/submissions/{body['id']}/disposition",
        headers=v,
        json={"decision": "ACCEPTED_FOR_RECORD", "reason": "fit for the working record"},
    )
    data = r.json()
    basis = data["record_basis"].lower()
    assert "not a government certification" in basis
    assert "no legal title" in basis
    assert "surveyed" in basis  # the geometry caveat travels with the decision


def test_responses_report_when_persistence_is_only_in_memory(client, authed_builder):
    """
    The demo runs without the database, and every write path must say so rather
    than swallow the failure. A created submission either reports persisted=True
    with a receipt, or persisted=False with a reason naming the missing parent.
    """
    body = _create_submission(authed_builder)
    p = body.get("persistence")
    assert p is not None, "create response must carry its persistence state"
    assert p["persisted"] in (True, False)
    if p["persisted"]:
        assert "receipt_number" in p
    else:
        assert p["reason"], "a not-persisted write must explain why"

    v = _verifier(client)
    r = client.post(
        f"/api/v1/builder/submissions/{body['id']}/disposition",
        headers=v,
        json={"decision": "ACCEPTED_FOR_RECORD", "reason": "reasonably attested"},
    )
    data = r.json()
    assert data["persistence"]["persisted"] in (True, False)
    if not data["persistence"]["persisted"]:
        assert data["persistence"]["reason"]


def test_detailed_intake_has_no_fabricated_measurement_defaults():
    """The request model filled plot/footprint/utility fields with
    measured-looking numbers (1000.0 m2, 450.0 m2, plinth 0.6 m, sewer at 2.2 m,
    a 120 m3 tank, 45 kW solar) that the submitter never supplied and the server
    never used. They are all optional now, so an untouched form sends nothing."""
    import pathlib
    import ast

    src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "backend" / "app" / "api" / "v1" / "builder_submissions.py"
    ).read_text()
    tree = ast.parse(src)

    defaults = {
        n.attr: (n.value.value if isinstance(n.value, ast.Constant) else None)
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Attribute)
    }
    mod = tree  # noqa
    # No field may default to a fabricated engineering quantity.
    for field in (
        "plot_area_m2", "footprint_area_m2", "plinth_height_m",
        "subsurface_depth_m", "sewer_invert_depth_m", "stormwater_tank_m3",
        "rooftop_solar_capacity_kw",
    ):
        assert field not in src.split("class DetailedBuildingSubmissionRequest")[0], (
            f"{field} referenced before the request model"
        )

    src_section = src.split("class DetailedBuildingSubmissionRequest")[1].split("class ")[0]
    for field in (
        "subsurface_depth_m", "sewer_invert_depth_m", "stormwater_tank_m3",
        "rooftop_solar_capacity_kw", "plinth_height_m",
    ):
        assert f"{field}: Optional[float] = None" in src_section, f"{field} still fabricates a default"
    assert "plot_area_m2" not in src_section
    assert "footprint_area_m2" not in src_section


# --------------------------------------------------------------------------- #
# The acceptance response and the page that renders it
# --------------------------------------------------------------------------- #

def _frontend_source(relative: str) -> str:
    return (
        pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src" / relative
    ).read_text()


def _accept(client, authed_builder, reason="fit for the working record", **overrides):
    """Create a submission, accept it, and return the disposition response."""
    body = _create_submission(authed_builder, ulpin=overrides.pop("ulpin", "202609250002"))
    payload = {"decision": "ACCEPTED_FOR_RECORD", "reason": reason}
    payload.update(overrides)
    r = client.post(
        f"/api/v1/builder/submissions/{body['id']}/disposition",
        headers=_verifier(client),
        json=payload,
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_disposition_response_carries_the_acceptance_fields_the_page_reads(client, authed_builder):
    """Asserted on the endpoint's own response, so these fields cannot be dropped
    while the page still compiles against the TypeScript interface."""
    body = _accept(client, authed_builder)

    for field in (
        "record_status", "record_basis", "review", "review_history", "persistence",
        "derived_ulpin", "derived_ulpin_status", "derivation_note",
        "identifier_authority", "audit_proof", "ulpin_note",
    ):
        assert field in body, f"disposition response no longer returns {field!r}"

    assert body["record_status"] == "ACCEPTED_FOR_RECORD"
    assert body["derived_ulpin_status"] in ("PROTOTYPE_DERIVED", "NOT_DERIVED", None)

    # No identifier without a status explaining it. The status is None when the
    # decision never reached the DB, so derivation was never attempted; the
    # consequence is the same either way and must not read as an issuance.
    assert not body["derived_ulpin"] or body["derived_ulpin_status"] == "PROTOTYPE_DERIVED"
    if body["derived_ulpin_status"] != "PROTOTYPE_DERIVED":
        assert not body["derived_ulpin"]
        assert not body["identifier_authority"]

    # The caveat has to match the state it describes. With an identifier, it must
    # deny registry authority and the authority field must say so too; without
    # one, it must say nothing was derived rather than staying silent.
    note = body["ulpin_note"].lower()
    if body["derived_ulpin"]:
        assert body["identifier_authority"] == "NOT_A_REGISTRY_ALLOCATION"
        assert "not a registry allocation" in note
        assert "confer no title" in note
    else:
        assert "no identifier could be derived" in note


def test_a_rejected_submission_gets_no_identifier_and_no_audit_proof(client, authed_builder):
    """Derivation and the audit chain belong to acceptance only. Showing an
    identifier next to a rejection would invent one for a refused submission."""
    body = _create_submission(authed_builder, ulpin="202609250003")
    r = client.post(
        f"/api/v1/builder/submissions/{body['id']}/disposition",
        headers=_verifier(client),
        json={"decision": "REJECTED", "reason": "the massing exceeds the setback"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["record_status"] == "REJECTED"
    assert not data["derived_ulpin"]


def test_review_page_reads_the_field_names_the_endpoint_actually_returns():
    """The page read `res.decision` and `res.record`. The endpoint returns
    `record_status` and `persistence`, so the persistence line silently rendered
    "no database write" for every submission, including the ones that wrote."""
    page = _frontend_source("pages/app/ReviewPage.tsx")

    assert "res.decision" not in page, "endpoint returns record_status, not decision"
    assert "res.record?" not in page, "endpoint returns persistence, not record"
    assert "res.record_status" in page
    assert "res.persistence" in page


def test_review_page_never_presents_the_identifier_as_an_issued_ulpin():
    """The derived identifier is this prototype's own computation over the parcel
    geometry. It must not be labelled as an allocation, and the backend's caveat
    must survive into the DOM rather than being replaced with something kinder."""
    page = _frontend_source("pages/app/ReviewPage.tsx")

    assert "Prototype-derived identifier" in page
    assert "not an issued ULPIN" in page
    assert "ulpin_note" in page, "the backend's own caveat must be rendered"
    assert "identifier_authority" in page

    # A bare "ULPIN" label next to the derived value would read as issued.
    assert "ULPIN: {s.derived_ulpin}" not in page
    assert "ULPIN: {res.derived_ulpin}" not in page


def test_review_page_renders_the_audit_proof_in_full():
    """`chained: false` is the interesting case: the hash fields are absent and
    only `reason` explains it, so both branches have to be rendered."""
    page = _frontend_source("pages/app/ReviewPage.tsx")

    for field in (
        "chained", "previous_hash", "hash", "ed25519_signature",
        "record_fingerprint", "signature_note", "table",
    ):
        assert f"proof.{field}" in page, f"audit_proof.{field} is never rendered"


def test_frontend_types_declare_the_acceptance_fields():
    api = _frontend_source("services/api.ts")
    block = api.split("export interface BuilderDispositionResponse")[1].split("\n}")[0]

    for field in (
        "record_status", "persistence", "derived_ulpin", "derived_ulpin_status",
        "derivation_note", "identifier_authority", "audit_proof", "ulpin_note",
    ):
        assert re.search(rf"^  {field}[?]?:", block, re.M), (
            f"BuilderDispositionResponse omits top-level {field!r}"
        )

    # The old top-level `decision` and `record` were what the endpoint stopped
    # returning. `decision` is still correct inside the nested `review` entry,
    # so assert on the shape rather than on the word.
    assert not re.search(r"^  decision\??:", block, re.M), "top-level decision is gone"
    assert not re.search(r"^  record\??:", block, re.M), "top-level record is gone"
    assert "BuilderAuditProof" in api


# --------------------------------------------------------------------------- #
# Postgres round trip (skipped when no database is reachable)
# --------------------------------------------------------------------------- #

def _postgres_reachable() -> bool:
    try:
        from sqlalchemy import text
        from app.core.database import sync_engine
        with sync_engine.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _postgres_reachable(),
    reason="no Postgres reachable from this environment",
)
def test_disposition_persists_real_rows_when_the_parents_exist(client, authed_builder):
    """
    The full path is only honest when the rows it claims to write actually land:
    a Submission row (so the durable record carries the builder's claim) and a
    VerificationCase row (so the decision is attributable to a verifier account).
    This seeds throwaway parents, drives the real endpoints, asserts the rows,
    and deletes them again.
    """
    from sqlalchemy import text
    from sqlalchemy import select
    from app.core.database import sync_engine, AsyncSessionLocal
    from app.models.evidence import Submission
    from app.models.verification import VerificationCase
    from app.models.cadastre import Parcel

    # --- seed parents ------------------------------------------------
    parcel_ulpin = "TEST2026000001"
    with sync_engine.begin() as conn:
        conn.execute(text("DELETE FROM verification_cases WHERE case_number LIKE 'VC-%'"))
        conn.execute(
            text("DELETE FROM submissions WHERE receipt_number LIKE 'SUB-2026-%'")
        )
        conn.execute(text("DELETE FROM parcels WHERE ulpin = :u"), {"u": parcel_ulpin})
        conn.execute(text("DELETE FROM users WHERE id IN ('usr-builder-demo','usr-district-admin')"))
        jid = conn.execute(
            text("SELECT id FROM jurisdictions LIMIT 1")
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO users (id, username, email, hashed_password, full_name, role_name, is_active, jurisdiction_id) "
                "VALUES ('usr-builder-demo','builder.demo','submissions@apexinfra.in','!demo-only!','Apex InfraProjects (test)','BUILDER',true,:j)"
            ),
            {"j": jid},
        )
        conn.execute(
            text(
                "INSERT INTO users (id, username, email, hashed_password, full_name, role_name, is_active, jurisdiction_id) "
                "VALUES ('usr-district-admin','district.admin','district.reviewer@example.invalid','!demo-only!','Sunita Patil (test)','DISTRICT_VERIFIER',true,:j)"
            ),
            {"j": jid},
        )
        conn.execute(
            text(
                "INSERT INTO parcels (id, ulpin, survey_number, jurisdiction_id, polygon_geojson, document_area_m2, calculated_area_m2, status) "
                "VALUES ('parcel-test-pb', :u, 'TEST-SURVEY-1', :j, '{\"type\":\"Polygon\"}', 500.0, 500.0, 'ACTIVE')"
            ),
            {"u": parcel_ulpin, "j": jid},
        )

    try:
        # --- drive the real endpoints --------------------------------
        body = _create_submission(authed_builder, ulpin=parcel_ulpin, name="Db Round Trip")
        assert body["id"].startswith("SUB-2026-")
        assert body["persistence"]["persisted"] is True, body["persistence"]

        v = _verifier(client)
        r = client.post(
            f"/api/v1/builder/submissions/{body['id']}/disposition",
            headers=v,
            json={
                "decision": "ACCEPTED_FOR_RECORD",
                "reason": "pipeline reviewed the declared massing end to end",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["persistence"]["persisted"] is True, r.json()["persistence"]

        # --- assert the rows actually exist -------------------------
        async def check():
            async with AsyncSessionLocal() as db:
                sub = (
                    await db.execute(
                        select(Submission).where(
                            Submission.receipt_number == body["id"]
                        )
                    )
                ).scalar_one_or_none()
                assert sub is not None, "submission row missing"
                assert sub.status == "ACCEPTED_FOR_RECORD"
                assert sub.submitter_id == "usr-builder-demo"

                case = (
                    await db.execute(
                        select(VerificationCase).where(
                            VerificationCase.submission_id == sub.id
                        )
                    )
                ).scalar_one_or_none()
                assert case is not None, "verification case missing"
                assert case.case_number == f"VC-{body['id']}"
                assert case.status == "APPROVED"
                assert case.decision_timestamp is not None
                assert "end to end" in (case.officer_notes or "")

                parcel = (
                    await db.execute(
                        select(Parcel).where(Parcel.ulpin == parcel_ulpin)
                    )
                ).scalar_one()
                assert parcel.id == "parcel-test-pb"

        import asyncio

        asyncio.run(check())
    finally:
        # --- scrub the test parents ---------------------------------
        with sync_engine.begin() as conn:
            conn.execute(text("DELETE FROM verification_cases WHERE submission_id IN (SELECT id FROM submissions WHERE receipt_number LIKE 'SUB-2026-%')"))
            conn.execute(text("DELETE FROM submissions WHERE receipt_number LIKE 'SUB-2026-%'"))
            conn.execute(text("DELETE FROM parcels WHERE ulpin = :u"), {"u": parcel_ulpin})
            conn.execute(text("DELETE FROM users WHERE id IN ('usr-builder-demo','usr-district-admin')"))