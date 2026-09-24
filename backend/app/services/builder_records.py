"""Postgres persistence for builder submissions and their review lifecycle.

Every write here is best-effort and reported honestly. The builder flow must
keep working when Postgres is unreachable or when the parent rows (the parcel,
the submitter) do not exist yet, so a call that cannot persist returns
``persisted=False`` with a reason instead of pretending a write happened. A
submission that only exists in the in-memory store is a real submission of the
demo; it is just not copied into the database until every foreign key it needs
is present.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from app.core import geometry


async def persist_submission_row(
    db,
    *,
    submission_id: str,
    project_name: str,
    parcel_ulpin: str,
    structure_code: Optional[str],
    submission_type: str,
    status: str,
    fsi_proposed: Optional[float],
    floors_proposed: Optional[int],
    remarks: str,
    submitter_id: str,
) -> Dict[str, Any]:
    """Copies a submission into Postgres when the submitter and parcel exist.

    The missing-parent case is reported, not papered over: creating a Parcel
    would require fabricating a survey number and an area, and a User row would
    be a self-declared identity wearing a real account. Neither is inserted
    here.
    """
    from app.models.evidence import Submission
    from app.models.cadastre import Parcel
    from app.models.user import User

    from app.core.cadastre_store import ensure_schema

    try:
        await ensure_schema(db)
        parcel = (
            await db.execute(select(Parcel).where(Parcel.ulpin == parcel_ulpin))
        ).scalar_one_or_none()
        if parcel is None:
            return {
                "persisted": False,
                "table": "submissions",
                "reason": "the parcel is not recorded in the database yet; submission kept in memory only",
            }
        submitter = (
            await db.execute(select(User).where(User.id == submitter_id))
        ).scalar_one_or_none()
        if submitter is None:
            return {
                "persisted": False,
                "table": "submissions",
                "reason": "the submitter is not a database account yet; submission kept in memory only",
            }
    except Exception as exc:  # connection failure etc.
        return {
            "persisted": False,
            "table": "submissions",
            "reason": f"database unreachable ({type(exc).__name__}); submission kept in memory only",
        }

    existing = (
        await db.execute(select(Submission).where(Submission.receipt_number == submission_id))
    ).scalar_one_or_none()
    if existing is None:
        existing = Submission(
            receipt_number=submission_id,
            submitter_id=submitter.id,
            parcel_id=parcel.id,
            contributor_type="BUILDER",
            status=status,
            declared_data={
                "project_name": project_name,
                "structure_code": structure_code,
                "submission_type": submission_type,
                "fsi_proposed": fsi_proposed,
                "floors_proposed": floors_proposed,
                "remarks": remarks,
            },
        )
        db.add(existing)
    else:
        existing.status = status
        existing.declared_data = {
            "project_name": project_name,
            "structure_code": structure_code,
            "submission_type": submission_type,
            "fsi_proposed": fsi_proposed,
            "floors_proposed": floors_proposed,
            "remarks": remarks,
        }
    await db.commit()
    return {"persisted": True, "table": "submissions", "receipt_number": submission_id}


async def apply_review_decision(
    db,
    *,
    submission_id: str,
    parcel_ulpin: str,
    decision: str,
    reason: str,
    basis: str,
    reviewer_id: str,
) -> Dict[str, Any]:
    """Records a reviewer's decision as a VerificationCase row when it can.

    The decision itself is made and returned regardless; this only fails to
    copy it into Postgres when a required parent (parcel, submission row,
    reviewer account) is absent, which is reported.
    """
    from app.models.cadastre import Parcel
    from app.models.evidence import Submission
    from app.models.verification import VerificationCase
    from app.models.user import User

    from app.core.cadastre_store import ensure_schema

    now = datetime.now(timezone.utc)

    try:
        await ensure_schema(db)
        parcel = (
            await db.execute(select(Parcel).where(Parcel.ulpin == parcel_ulpin))
        ).scalar_one_or_none()
        submission = (
            await db.execute(select(Submission).where(Submission.receipt_number == submission_id))
        ).scalar_one_or_none()
        reviewer = (
            await db.execute(select(User).where(User.id == reviewer_id))
        ).scalar_one_or_none()
        if parcel is None or submission is None or reviewer is None:
            missing = [
                name
                for name, found in (
                    ("parcel", parcel is not None),
                    ("submission row", submission is not None),
                    ("reviewer account", reviewer is not None),
                )
                if not found
            ]
            return {
                "persisted": False,
                "table": "verification_cases",
                "reason": f"decision kept in memory only; missing {', '.join(missing)} in the database",
            }
    except Exception as exc:
        return {
            "persisted": False,
            "table": "verification_cases",
            "reason": f"database unreachable ({type(exc).__name__}); decision kept in memory only",
        }

    case = (
        await db.execute(
            select(VerificationCase).where(VerificationCase.submission_id == submission.id)
        )
    ).scalar_one_or_none()
    if case is None:
        case = VerificationCase(
            case_number=f"VC-{submission_id}",
            parcel_id=parcel.id,
            submission_id=submission.id,
            assigned_verifier_id=reviewer.id,
            case_type="BUILDER_SUBMISSION_REVIEW",
            priority="HIGH",
            status="APPROVED" if decision == "ACCEPTED_FOR_RECORD" else "REJECTED",
            officer_notes=reason,
            basis=basis or None,
            decision_timestamp=now,
        )
        db.add(case)
    else:
        case.assigned_verifier_id = reviewer.id
        case.status = "APPROVED" if decision == "ACCEPTED_FOR_RECORD" else "REJECTED"
        case.officer_notes = reason
        case.basis = basis or None
        case.decision_timestamp = now
    submission.status = "ACCEPTED_FOR_RECORD" if decision == "ACCEPTED_FOR_RECORD" else "REJECTED"
    await db.commit()

    derived = await _derive_record_on_acceptance(
        db,
        parcel=parcel,
        submission_id=submission_id,
        parcel_ulpin=parcel_ulpin,
        decision=decision,
        reason=reason,
        reviewer_id=reviewer_id,
        now=now,
    )

    return {
        "persisted": True,
        "table": "verification_cases",
        "case_number": case.case_number,
        "decision_timestamp": now.isoformat(),
        **derived,
    }


# What the identifier below is, stated in the payload itself.
#
# The prompt this came from called it an "official 3D-ULPIN" and told the UI
# to render it under a heading reading "Official 3D-ULPIN". That is not what it
# is. `parcel_ulpin_from_vertices` is a deterministic function of the geometry:
# no state registry was contacted, nothing was allocated, and no title moves.
# app.id_engine.national states this in its own module docstring -- official
# issuance has to come from the DOLR/state ULPIN API. So the payload carries
# PROVENANCE and AUTHORITY explicitly, and the response repeats it, rather than
# relying on a UI label that anyone can edit away from the data.
_IDENTITY_BASIS = "PROTOTYPE_DERIVED_FROM_PARCEL_GEOMETRY"
_IDENTITY_AUTHORITY = "NOT_A_REGISTRY_ALLOCATION"


async def _derive_record_on_acceptance(
    db,
    *,
    parcel,
    submission_id: str,
    parcel_ulpin: str,
    decision: str,
    reason: str,
    reviewer_id: str,
    now: datetime,
) -> Dict[str, Any]:
    """Derives a prototype identifier and chains an audit event on acceptance.

    Everything here is best-effort and reports why it could not do its work.
    A reviewer accepting a submission is a real decision that has already been
    persisted by the caller, so a failure to derive an identifier must not undo
    it -- but it must not be silent either, or the response would imply a proof
    that does not exist.
    """
    if decision != "ACCEPTED_FOR_RECORD" or parcel is None:
        return {}

    derived_ulpin = None
    has_geometry = getattr(parcel, "geom", None) is not None
    derivation_note = (
        "The accepted parcel has geometry, but it is not in a projected "
        "coordinate system this prototype can convert, so no identifier was "
        "derived. The review decision itself is recorded."
        if has_geometry
        else "Parcel geometry is not available, so no identifier could be derived. "
        "The review decision itself is recorded."
    )

    # 1. Derive the identifier from the persisted parcel geometry.
    try:
        from app.id_engine.national import parcel_ulpin_from_vertices

        ring = _parcel_ring(parcel)
        if ring:
            derived_ulpin, derivation = parcel_ulpin_from_vertices(ring)
            derivation_note = (
                "Derived deterministically from the accepted parcel's geometry "
                "by this prototype. No state registry was contacted and no "
                "allocation was made." + _anchor_caveat(parcel)
            )
        else:
            derivation = None
            # Distinguish "no geometry" from "geometry we cannot trust": a
            # builder-drawn footprint is stored as local-frame metres, and a
            # ULPIN from those would name a place on Earth other than this
            # parcel. Saying which of the two happened is the difference
            # between a fixable data problem and an invisible wrong answer.
            if getattr(parcel, "geom", None) is not None or getattr(parcel, "polygon_geojson", None):
                derivation_note = (
                    "The accepted parcel has geometry, but it is not stored as "
                    "georeferenced coordinates this identifier can be derived "
                    "from. No identifier was minted rather than derive one that "
                    "would not refer to this parcel. The review decision itself "
                    "is recorded."
                )
    except Exception as exc:
        derivation = None
        derivation_note = f"Identifier derivation failed ({type(exc).__name__}); the review decision is recorded."

    # 2. Chain an audit event.
    #
    # The head is read inside append_audit_event, from the newest event rather
    # than pinned to the genesis sentinel. Every record pointing at genesis makes
    # the "chain" a bag of unrelated hashes that each verify in isolation, which
    # is the one thing a tamper-evident chain exists to prevent.
    audit = {"chained": False, "reason": "audit event could not be written"}
    try:
        from app.core.audit_chain import append_audit_event

        # Routed through append_audit_event rather than building AuditEvent here.
        # This used to compute its own chain head with a separate query, which
        # was a second source of truth: it ignored the NULL event_number rows
        # written by the 47 legacy events, so it could link onto a stale parent
        # and fork the chain, and it never assigned event_number at all.
        payload = {
            "submission_id": submission_id,
            "parcel_ulpin": parcel_ulpin,
            "decision": decision,
            "reason": reason,
            "derived_ulpin": derived_ulpin,
            "basis": _IDENTITY_BASIS,
            "authority": _IDENTITY_AUTHORITY,
        }
        event = await append_audit_event(
            db,
            event_type="SUBMISSION_ACCEPTED",
            entity_type="BUILDER_SUBMISSION",
            entity_id=submission_id,
            actor_id=reviewer_id,
            timestamp_iso=now.isoformat(),
            payload=payload,
        )
        previous_hash = event.previous_hash
        current_hash = event.current_hash
        audit = {
            "chained": True,
            "previous_hash": previous_hash,
            "hash": current_hash,
            "event_type": "SUBMISSION_ACCEPTED",
            "timestamp": now.isoformat(),
            "table": "audit_events",
        }
    except Exception as exc:
        audit = {"chained": False, "reason": f"audit event could not be written ({type(exc).__name__})"}
        await db.rollback()

    # 3. Sign the acceptance record.
    #
    # sign_canonical_record returns a (fingerprint, signature) tuple. The
    # original version of this called .get("signature_hex") on it, raised
    # AttributeError, and hid the failure in a bare `except: pass` -- so the
    # signature silently never appeared and nothing was wrong for a user who
    # only ever saw the happy path.
    signature: Optional[str] = None
    fingerprint: Optional[str] = None
    signing_record = {
        "submission_id": submission_id,
        "decision": decision,
        "reviewer": reviewer_id,
        "timestamp": now.isoformat(),
        "derived_ulpin": derived_ulpin,
        "basis": _IDENTITY_BASIS,
        "authority": _IDENTITY_AUTHORITY,
    }
    try:
        from app.core.crypto import sign_canonical_record

        fingerprint, signature = sign_canonical_record(signing_record)
    except Exception:
        fingerprint = None
        signature = None

    return {
        "derived_ulpin": derived_ulpin,
        "derived_ulpin_status": "PROTOTYPE_DERIVED" if derived_ulpin else "NOT_DERIVED",
        "derivation": derivation,
        "derivation_note": derivation_note,
        "identifier_authority": _IDENTITY_AUTHORITY,
        "blockchain_proof": {
            **audit,
            "ed25519_signature": signature,
            "record_fingerprint": fingerprint,
            "signature_note": (
                "Ed25519 over this prototype's own key. It proves the record has "
                "not been altered since signing; it is not a government seal and "
                "carries no authority over the parcel."
            ),
        },
    }


def _parcel_ring(parcel) -> Optional[list]:
    """Exterior ring of a persisted parcel as (lat, lon) pairs, or None.

    `parcel_ulpin_from_vertices` hashes *georeferenced degrees*: it picks a
    degree-cell band from the centroid and rounds vertices to 1e-6 deg. Any
    other input still yields a stable 14-character string, just one naming the
    wrong place, so this only hands over coordinates it can vouch for.

    Read from `polygon_geojson` (WGS84, [lon, lat]) rather than the PostGIS
    `geom` column. Two earlier versions read `parcel.geometry`, which is not a
    column at all, and then reprojected `geom` as if it were sound UTM 43N. It
    is not: the stored rows were the Airoli UTM origin (298000, 2113500) plus
    the longitude/latitude *degrees* added to it, which lands tens of
    kilometres from the footprint the same row describes. Reprojecting that
    would have produced a well-formed identifier for the wrong parcel.

    The frame test is :func:`app.core.geometry.classify_frame`, the same one the
    write paths use, so what is written into `polygon_geojson` and what is read
    back here can never disagree about what a number means. Builder footprints
    reach that column as real degrees now (the write anchors the drawing to the
    documented origin first), but a row written before that fix still holds bare
    metres -- and those are refused here, because no ULPIN can honestly be
    derived from a coordinate whose frame is unknown.
    """
    ring = geometry.geojson_exterior_ring(getattr(parcel, "polygon_geojson", None))
    if len(ring) < 3:
        return None
    if not geometry.is_georeferenced(ring):
        return None
    # Drop a repeated closing vertex; the engine canonicalises anyway.
    if ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        return None
    return [(lat, lon) for lon, lat in ring]


def _anchor_caveat(parcel) -> str:
    """Says so when the geometry's position is an assumption, and returns '' otherwise."""
    detail = getattr(parcel, "provenance_detail", None)
    if not isinstance(detail, dict):
        return ""
    if detail.get("geometry_frame") != geometry.FRAME_LOCAL_METRES:
        return ""
    return (
        " The parcel's own position is an assumption rather than a survey: the "
        "submitter drew the footprint in the local metre frame and it was placed "
        "at the documented Airoli UTM zone 43N origin, so these coordinates name "
        "an approximate location, not a measured one."
    )


async def persist_builder_structure(
    db,
    *,
    ulpin: str,
    project_name: str,
    structure_code: str,
    structure_type: str,
    floors_above_ground: int,
    floor_to_floor_height_m: float,
    total_height_m: float,
    footprint_ring: list,
    address: Optional[str],
    locality: Optional[str],
    ground_z: float,
    floor_labels: Optional[list] = None,
) -> Dict[str, Any]:
    """Writes a builder's declared massing as real Parcel + Structure + Level rows.

    The rows are marked demo-generated and non-authoritative where they came
    from the submitter (the parcel is whatever the submitter drew; the height
    basis is a declaration). No units are invented: a level exists because the
    submitter named it, a unit would be a subdivision nobody subdivided.

    The drawn footprint is anchored rather than stored raw, and that choice is
    argued at the point of the write below.
    """
    from app.models.cadastre import Parcel, Structure, Level
    from app.core.cadastre_store import (
        polyhedral_surface_wkt,
        shoelace_area_m2,
        ensure_schema,
        AIROLI_ORIGIN,
    )

    try:
        await ensure_schema(db)
    except Exception as exc:
        return {
            "persisted": False,
            "table": "structures",
            "reason": f"database unreachable ({type(exc).__name__}); massing kept in memory only",
        }

    ring = [tuple(float(v) for v in p) for p in footprint_ring]
    if len(ring) < 3:
        return {
            "persisted": False,
            "table": "structures",
            "reason": "footprint requires at least 3 vertices",
        }

    # The demo jurisdiction ("jur-airoli-sec08") exists only in the auth layer,
    # not necessarily as a database row. A parcel write needs a real
    # jurisdiction for the foreign key, so fall back to whatever jurisdiction
    # the store actually has and say which one was used.
    from sqlalchemy import text as sqltext

    try:
        jurisdiction_id = (
            await db.execute(sqltext("SELECT id FROM jurisdictions WHERE id = 'jur-airoli-sec08'"))
        ).scalar_one_or_none()
        if jurisdiction_id is None:
            jurisdiction_id = (
                await db.execute(sqltext("SELECT id FROM jurisdictions LIMIT 1"))
            ).scalar_one_or_none()
    except Exception as exc:
        return {
            "persisted": False,
            "table": "structures",
            "reason": f"no jurisdiction context in the database ({type(exc).__name__})",
        }
    if not jurisdiction_id:
        return {
            "persisted": False,
            "table": "structures",
            "reason": "no jurisdiction context in the database",
        }

    # ------------------------------------------------------------------ #
    # Where the drawn ring actually is, and where it is put.
    #
    # The submitter's footprint is LOCAL-FRAME METRES: the builder studio's
    # picker and polygon editor work in metres from the precinct datum
    # (DEFAULT_FOOTPRINT is [[0,0],[24,0],[24,12],[0,12]]), and this value
    # arrives as `footprint_ring`. The old code did
    # `parcel.geom = polygon_wkt(ring)` and also copied those same metres into
    # `polygon_geojson`. Both were lies: a 32643 column received bare metres,
    # and a column whose name promises WGS84 degrees received metres, so the
    # two halves of the row disagreed by tens of kilometres and every reader
    # downstream had to guess which one to believe.
    #
    # Option (b) -- leave `geom` NULL and keep the drawing out of GeoJSON --
    # was the alternative. Rejected because this row's own 3D solid already
    # lives in that frame: `geom_3d` below is built by polyhedral_surface_wkt,
    # which places the same ring at the same documented Airoli origin. Refusing
    # to place the parcel would leave the parcel and its structure describing
    # two different places, and would leave ST_Area, the tile layer and the map
    # with nothing to read. Anchoring also keeps every area figure exact --
    # shoelace over metres is 288.0 for a 24x12 rectangle, and the reprojected
    # polygon measures the same to the millimetre.
    #
    # So: anchor explicitly, convert to real WGS84 for `polygon_geojson`, and
    # record on the row that the position is an assumption
    # (`provenance_detail`, geometry.ANCHOR_NOTE) rather than a survey.
    origin = (float(AIROLI_ORIGIN["easting"]), float(AIROLI_ORIGIN["northing"]))
    try:
        anchored_ring = geometry.anchor_local_ring(ring, origin)
        geodetic_ring = geometry.utm43n_ring_to_wgs84(anchored_ring)
        parcel_ewkt = geometry.utm43n_polygon_ewkt(anchored_ring)
    except geometry.GeometryRefused as exc:
        return {
            "persisted": False,
            "table": "structures",
            "reason": f"footprint could not be placed on the map ({exc})",
        }
    closed_geodetic = geodetic_ring + [geodetic_ring[0]]
    parcel_geojson = {
        "type": "Polygon",
        "coordinates": [[[round(lon, 9), round(lat, 9)] for lon, lat in closed_geodetic]],
    }

    parcel = (
        await db.execute(select(Parcel).where(Parcel.ulpin == ulpin))
    ).scalar_one_or_none()
    if parcel is None:
        area = shoelace_area_m2(ring)
        parcel = Parcel(
            ulpin=ulpin,
            survey_number=None,
            jurisdiction_id=jurisdiction_id,
            polygon_geojson=parcel_geojson,
            document_area_m2=area,
            calculated_area_m2=area,
            status="PENDING_SURVEY",
            data_provenance="demo-generated",
            provenance_authoritative=False,
            address=address,
            locality=locality,
        )
        db.add(parcel)
        await db.flush()
    else:
        parcel.address = parcel.address or address
        parcel.locality = parcel.locality or locality
        # Refresh both halves: a row written before this fix still holds metres
        # in `polygon_geojson`, and leaving them would keep the disagreement.
        parcel.polygon_geojson = parcel_geojson

    parcel.geom = parcel_ewkt
    parcel.provenance_detail = {
        **(parcel.provenance_detail or {}),
        **geometry.anchor_record(origin),
    }
    # gis_area_m2 is the PostGIS measurement over the geometry actually stored.
    # It is only written when that geometry exists, so it can never carry a
    # measured 0.0 for a parcel that was never projected.
    await db.flush()
    measured = (
        await db.execute(select(func.ST_Area(parcel.geom)))
    ).scalar()
    if measured is not None:
        parcel.gis_area_m2 = round(float(measured), 2)

    structure = (
        await db.execute(
            select(Structure).where(
                Structure.parcel_id == parcel.id,
                Structure.building_code == structure_code,
            )
        )
    ).scalar_one_or_none()
    if structure is None:
        structure = Structure(
            parcel_id=parcel.id,
            building_code=structure_code,
            name=project_name,
            structure_type=structure_type,
            footprint_geojson={
                "type": "Polygon",
                "coordinates": [[[float(x), float(y)] for x, y in ring]],
            },
            ground_elevation_z=ground_z,
            height_m=max(total_height_m, 0.1),
            floors_count=max(1, floors_above_ground),
            basements_count=0,
            total_built_up_area_m2=round(shoelace_area_m2(ring) * floors_above_ground, 2),
            calculated_fsi=None,
            is_verified=False,
            data_provenance="demo-generated",
            provenance_authoritative=False,
            height_basis="declared_by_submitter",
            geom_3d=polyhedral_surface_wkt(ring, ground_z, ground_z + max(total_height_m, 3.6)),
        )
        db.add(structure)
        await db.flush()
    else:
        structure.height_m = max(total_height_m, 0.1)
        structure.floors_count = max(1, floors_above_ground)
        structure.height_basis = "declared_by_submitter"
        structure.is_verified = False

    labels = list(floor_labels or [])
    existing_lc = {
        l.level_code
        for l in (
            await db.execute(select(Level).where(Level.structure_id == structure.id))
        ).scalars().all()
    }
    for idx in range(max(1, floors_above_ground)):
        level_code = labels[idx]["level_code"] if idx < len(labels) else f"L{idx + 1:02d}"
        if level_code in existing_lc:
            continue
        min_z = ground_z + idx * floor_to_floor_height_m
        level = Level(
            structure_id=structure.id,
            level_code=level_code,
            floor_number=idx + 1,
            min_z=round(min_z, 3),
            max_z=round(min_z + floor_to_floor_height_m, 3),
            height_m=floor_to_floor_height_m,
            level_type="HABITABLE",
            name=(labels[idx].get("name") if idx < len(labels) else None),
            use=(labels[idx].get("use") if idx < len(labels) else None),
            boundary_geojson={"type": "Polygon", "coordinates": [[[float(x), float(y)] for x, y in ring]]},
            geom_3d=polyhedral_surface_wkt(ring, min_z, min_z + floor_to_floor_height_m),
        )
        db.add(level)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        return {
            "persisted": False,
            "table": "structures",
            "reason": f"write failed ({type(exc).__name__}); massing kept in memory only",
        }
    return {
        "persisted": True,
        "table": "structures",
        "parcel_ulpin": parcel.ulpin,
        "structure_code": structure.building_code,
        "origin_offset": {"easting": AIROLI_ORIGIN["easting"], "northing": AIROLI_ORIGIN["northing"]},
        "parcel_geometry_basis": {
            "geometry_frame": geometry.FRAME_LOCAL_METRES,
            "georeferenced": False,
            "position_source": "documented Airoli UTM zone 43N origin, assumed",
            "crs": geometry.CRS_UTM43N,
            "note": geometry.ANCHOR_NOTE,
        },
        "gis_area_m2": parcel.gis_area_m2,
    }


def list_persisted_builder_structures() -> List[Dict[str, Any]]:
    """Builder-asserted structures, read synchronously for the precinct layer.

    /precinct endpoints are sync, so this uses the sync engine: it reports
    what the builder studio actually wrote (real rows, not the generated
    showcase cache), each with the parcel it sits on and its reviewer
    workflow status. Returns [] when the store is unreachable - a missing
    database is reported as absence, never invented content.
    """
    from app.core.database import sync_engine
    from sqlalchemy import text
    from app.core.cadastre_store import shoelace_area_m2

    try:
        with sync_engine.connect() as c:
            rows = c.execute(
                text(
                    """
                    SELECT s.id, s.building_code, s.name, s.structure_type,
                           s.height_m, s.floors_count, s.footprint_geojson,
                           s.calculated_fsi, s.data_provenance, s.height_basis,
                           s.is_verified,
                           p.ulpin, p.address, p.locality,
                           (SELECT sub.status FROM submissions sub
                             WHERE sub.parcel_id = p.id
                             ORDER BY sub.created_at DESC LIMIT 1) AS sub_status
                    FROM structures s
                    JOIN parcels p ON p.id = s.parcel_id
                    ORDER BY s.created_at
                    """
                )
            ).mappings().all()

            level_rows = c.execute(
                text(
                    """
                    SELECT structure_id, level_code, floor_number, name, use
                    FROM levels ORDER BY floor_number
                    """
                )
            ).mappings().all()
    except Exception:
        return []

    levels_by_structure: Dict[str, List[Dict[str, Any]]] = {}
    for lv in level_rows:
        levels_by_structure.setdefault(lv["structure_id"], []).append(
            {
                "level_code": lv["level_code"],
                "floor_number": lv["floor_number"],
                "name": lv["name"],
                "use": lv["use"],
            }
        )

    out: List[Dict[str, Any]] = []
    for r in rows:
        geojson = r["footprint_geojson"] or {}
        ring = (geojson.get("coordinates") or [[[0, 0]]])[0]
        xs = [float(px[0]) for px in ring]
        ys = [float(px[1]) for px in ring]
        footprint_area = shoelace_area_m2([(x, y) for x, y in zip(xs, ys)])
        out.append(
            {
                "code": r["building_code"],
                "name": r["name"],
                "type": r["structure_type"] or "tower",
                "floors": r["floors_count"],
                "height_m": r["height_m"] if r["height_m"] is not None else 0.0,
                "x": min(xs) if xs else 0.0,
                "y": min(ys) if ys else 0.0,
                "w": (max(xs) - min(xs)) if xs else 0.0,
                "h": (max(ys) - min(ys)) if ys else 0.0,
                "geometry_basis": "builder-asserted, not surveyed",
                "footprint_geojson": geojson,
                "footprint_area_m2": round(footprint_area, 2),
                "fsi": r["calculated_fsi"],
                "fsi_status": "NOT_VERIFIED" if r["calculated_fsi"] is None else None,
                "status": r["sub_status"] if r["sub_status"] else (
                    "VERIFIED" if r["is_verified"] else ("INFERRED" if r["data_provenance"] != "demo-generated" else "PENDING_REVIEW")
                ),
                "ulpin": r["ulpin"],
                "address": r["address"],
                "locality": r["locality"],
                "provenance": r["data_provenance"],
                "height_basis": r["height_basis"],
                "is_hero": False,
                "is_synthetic": False,
                "units_count": 0,
                "units": [],
                "levels": levels_by_structure.get(r["id"], []),
            }
        )
    return out
