from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.demo_gate import demo_mode_enabled
from app.core.cadastre_store import upsert_parcel, polygon_wkt, ensure_schema
from app.models.cadastre import Parcel, Structure, Level
from app.models.jurisdiction import Jurisdiction
from app.sources import NoAuthenticSourceError, fetch_area

router = APIRouter(prefix="/parcels", tags=["2D Cadastral Parcels"])


async def load_parcels(db: AsyncSession) -> List[Parcel]:
    """Every parcel in the cadastral store.

    Nothing is generated here: a parcel only exists if it was ingested from a
    published dataset (``POST /parcels/ingest-area``) or loaded by a seed
    script, and each row carries its own provenance.
    """
    await ensure_schema(db)
    result = await db.execute(select(Parcel).options(selectinload(Parcel.jurisdiction)))
    return list(result.scalars().all())


async def _structures_by_ulpin(db: AsyncSession) -> Dict[str, Structure]:
    rows = (
        await db.execute(select(Structure).options(selectinload(Structure.levels)))
    ).scalars().all()
    out: Dict[str, Structure] = {}
    for st in rows:
        parcel = await db.get(Parcel, st.parcel_id)
        if parcel is not None:
            out[parcel.ulpin] = st
    return out


async def _review_status_by_ulpin(db: AsyncSession) -> Dict[str, str]:
    """Latest reviewer workflow status per parcel, from real submission rows."""
    rows = (
        await db.execute(
            text(
                """
                SELECT p.ulpin AS ulpin, sub.status AS st
                FROM submissions sub
                JOIN parcels p ON p.id = sub.parcel_id
                JOIN (SELECT parcel_id, MAX(created_at) AS latest
                      FROM submissions GROUP BY parcel_id) latest
                  ON latest.parcel_id = sub.parcel_id
                 AND sub.created_at = latest.latest
                """
            )
        )
    ).mappings().all()
    return {r["ulpin"]: r["st"] for r in rows}


def _location_of(parcel: Parcel) -> Dict[str, Any]:
    """Administrative location read from the parcel's own jurisdiction row."""
    j = getattr(parcel, "jurisdiction", None)
    if j is None:
        return {}
    return {
        "state": j.state,
        "district": j.district,
        "taluka": j.taluka,
        "village_ward": j.village_ward,
        "jurisdiction_code": j.code,
    }


def _building_of(
    structure: Optional[Structure],
    parcel: Optional[Parcel] = None,
    record_status: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Structure as a map/registry summary, reported honestly.

    The previous status was a constant "SURVEYED" regardless of where the
    geometry came from. A builder's drawn footprint has never been surveyed,
    and an OSM/GlobalML extraction is inferred from tags, so each now says
    what it is: the reviewer workflow status when a submission row exists,
    VERIFIED only when a structure is actually marked verified, INFERRED for
    ingested sources, PENDING_REVIEW for builder-asserted rows.
    """
    if structure is None:
        return None
    if record_status:
        status = record_status
    elif structure.is_verified:
        status = "VERIFIED"
    elif structure.data_provenance == "demo-generated":
        status = "PENDING_REVIEW"
    else:
        status = "INFERRED"
    base = {
        "code": structure.building_code,
        "name": structure.name,
        "floors": structure.floors_count,
        "height_m": structure.height_m,
        "fsi": structure.calculated_fsi,
        "type": structure.structure_type,
        "status": status,
        "has_3d": True,
        "provenance": structure.data_provenance,
        "height_basis": structure.height_basis,
        "is_verified": bool(structure.is_verified),
        "levels": [
            {
                "level_code": lv.level_code,
                "floor_number": lv.floor_number,
                "name": lv.name,
                "use": lv.use,
            }
            for lv in (getattr(structure, "levels", None) or [])
        ],
    }
    if parcel is not None:
        base["address"] = parcel.address
        base["locality"] = parcel.locality
    return base


@router.get("/")
async def list_parcels(
    db: AsyncSession = Depends(get_db),
    state: str | None = None,
    district: str | None = None,
    taluka: str | None = None,
    village: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """
    Returns parcels in the precinct, with optional administrative filters
    (state / district / taluka / village*) and a free-text query against
    ULPIN or survey number. Matching is case-insensitive.

    * `village` matches either the village_ward name or its code.
    """
    parcels = await load_parcels(db)
    building_by_ulpin = await _structures_by_ulpin(db)
    review_status_by_ulpin = await _review_status_by_ulpin(db)

    haystack = (state or "").lower()
    needlem = (district or "").lower()
    needlet = (taluka or "").lower()
    needlev = (village or "").lower()
    query = (q or "").lower().strip()

    rows = []
    for p in parcels:
        loc = _location_of(p)
        if haystack and haystack not in (loc.get("state") or "").lower() and haystack != (loc.get("state_code") or "").lower():
            continue
        if needlem and needlem not in (loc.get("district") or "").lower() and needlem != (loc.get("district_code") or "").lower():
            continue
        if needlet and (needlet not in (loc.get("taluka") or "").lower() and needlet not in (loc.get("taluka_code") or "").lower()):
            continue
        if needlev and (needlev not in (loc.get("village_ward") or "").lower() and needlev not in (loc.get("village_code") or "").lower()):
            continue
        if query and query not in p.ulpin.lower() and query not in (p.survey_number or "").lower():
            continue
        rows.append({
            "id": p.id,
            "ulpin": p.ulpin,
            "survey_number": p.survey_number,
            "polygon_geojson": p.polygon_geojson,
            "document_area_m2": p.document_area_m2,
            "calculated_area_m2": p.calculated_area_m2,
            "status": p.status,
            "has_postgis_geom": p.geom is not None,
            "location": loc,
            "address": p.address,
            "locality": p.locality,
            "building": _building_of(
                building_by_ulpin.get(p.ulpin),
                parcel=p,
                record_status=review_status_by_ulpin.get(p.ulpin),
            ),
            "provenance": {
                "source": p.data_provenance,
                "authoritative": bool(p.provenance_authoritative),
            },
        })

    # If more records needed, fetch matching national_parcels from PostGIS
    #
    # Gated: national_parcels is synthetic and has been purged (0 rows), and the
    # national_twins it joins are synthetic too. Serving them here would re-expose
    # the generated grid, and re-running the seed script would silently repopulate
    # a default deployment.
    if not demo_mode_enabled():
        return rows[offset: offset + limit]

    remaining_limit = max(0, limit - len(rows))
    if remaining_limit > 0:
        import json
        from sqlalchemy import text
        conds = ["TRUE"]
        sql_params: Dict[str, Any] = {"limit": remaining_limit, "offset": offset}
        if state:
            conds.append("(p.state_code ILIKE :state OR :state ILIKE ('%' || p.state_code || '%'))")
            sql_params["state"] = f"%{state}%"
        if district:
            conds.append("(p.district_code ILIKE :district OR d.name ILIKE :district OR :district ILIKE ('%' || p.district_code || '%'))")
            sql_params["district"] = f"%{district}%"
        if taluka:
            conds.append("(p.boundary_code ILIKE :taluka OR t.name ILIKE :taluka OR t.code ILIKE :taluka)")
            sql_params["taluka"] = f"%{taluka}%"
        if village:
            conds.append("(p.boundary_code ILIKE :village OR b.name ILIKE :village OR b.code ILIKE :village)")
            sql_params["village"] = f"%{village}%"
        if query:
            conds.append("(p.ulpin ILIKE :q OR p.survey_number ILIKE :q OR w.name ILIKE :q OR b.name ILIKE :q)")
            sql_params["q"] = f"%{query}%"

        try:
            np_res = await db.execute(
                text(f"""
                    SELECT p.ulpin, p.survey_number, p.zonal_class, p.state_code, p.district_code, p.boundary_code,
                           ST_AsGeoJSON(p.geom) as geom_json, p.area_m2,
                           w.structure_code, w.name as b_name, w.typology, w.height_m, w.floors, w.fsi, w.fsi_status,
                           b.name as village_name, t.name as taluka_name, d.name as district_name
                    FROM national_parcels p
                    LEFT JOIN national_twins w ON w.ulpin = p.ulpin
                    LEFT JOIN admin_boundaries b ON b.code = p.boundary_code
                    LEFT JOIN admin_boundaries t ON t.code = b.parent_code
                    LEFT JOIN admin_boundaries d ON d.code = p.district_code
                    WHERE {' AND '.join(conds)}
                    ORDER BY p.ulpin ASC
                    LIMIT :limit OFFSET :offset
                """),
                sql_params
            )
            for row in np_res.fetchall():
                p_u, p_s, z_c, s_c, d_c, b_c, g_json, a_m2, w_code, w_name, w_typ, w_hm, w_fl, w_fsi, w_fst, v_n, t_n, d_n = row
                rows.append({
                    "id": f"national-{p_u}",
                    "ulpin": p_u,
                    "survey_number": p_s,
                    "polygon_geojson": json.loads(g_json) if g_json else None,
                    # These were `if a_m2 else 1000.0` and `CTS-<ulpinsuffix>`:
                    # an area or survey number from nowhere, printed as fact for
                    # a parcel the database did not measure. None is honest.
                    "document_area_m2": float(a_m2) if a_m2 else None,
                    "calculated_area_m2": float(a_m2) if a_m2 else None,
                    "status": "APPROVED",
                    "has_postgis_geom": True,
                    "location": {
                        "state": "Maharashtra" if s_c == "MH" else s_c,
                        "state_code": s_c,
                        "district": d_n or d_c,
                        "district_code": d_c,
                        "taluka": t_n or b_c,
                        "taluka_code": b_c,
                        "village_ward": v_n or b_c,
                        "jurisdiction_code": b_c,
                    },
                    "building": {
                        "code": w_code,
                        "name": w_name or f"Building {w_code}",
                        "floors": w_fl,
                        "height_m": w_hm,
                        "fsi": w_fsi,
                        "type": w_typ or "tower",
                        # Never default a missing compliance verdict to PASS:
                        # an absent record is not an approval. Only echo a value
                        # the source actually holds.
                        "status": w_fst,
                        "has_3d": True,
                    } if w_code else None,
                    "provenance": {
                        "source": "Synthesized PostGIS national_parcels (Boundary Grid Simulation)",
                        "authoritative": False,
                        "is_synthetic": True,
                    },
                })
        except Exception:
            pass

    return rows[offset: offset + limit]


@router.get("/geojson")
async def get_parcels_geojson(db: AsyncSession = Depends(get_db)):
    """
    Returns 2D Cadastre parcels as standard GeoJSON FeatureCollection
    for direct integration into MapLibre GL JS.
    """
    parcels = await load_parcels(db)

    # Real PostGIS-validated extents in projected metres (ST_Area over EPSG:32643).
    from sqlalchemy import func

    building_ulpins = set(await _structures_by_ulpin(db))

    features = []
    for p in parcels:
        has_twin = (p.ulpin in building_ulpins)
        gis_area = None
        if p.geom is not None:
            area = await db.execute(select(func.ST_Area(p.geom)))
            gis_area = round(float(area.scalar() or 0.0), 2)
        features.append({
            "type": "Feature",
            "id": p.ulpin,
            "geometry": p.polygon_geojson,
            "properties": {
                "ulpin": p.ulpin,
                "survey_number": p.survey_number,
                "document_area_m2": p.document_area_m2,
                "calculated_area_m2": p.calculated_area_m2,
                "gis_area_m2": gis_area,
                "has_3d_twin": has_twin,
                "status": p.status,
                "provenance": p.data_provenance,
                "persisted_in_postgis": True,
            },
        })

    return {"type": "FeatureCollection", "features": features}


async def _national_parcel_response(db: AsyncSession, ulpin: str) -> Optional[Dict[str, Any]]:
    """Return a national_parcels row, reporting only what the row actually holds.

    This branch used to fill every gap: four floors at 3.2 m when the source had
    no height, sixteen strata units with areas and volumes, an OWNERSHIP right for
    a "Registered Allottee" holding 100%, a permitted-FAR limit, an fsi_status
    computed against it, and ``status: "APPROVED"``. None of that was sourced.
    The 45,489 rows that reached here were procedurally generated rectangles
    (``seed_mumbai_metropolitan.py``, ``national_bulk.py``), 1,166 of them
    claiming ``MMRDA_CADASTRAL_DIRECT`` provenance; see
    ``app/cli/purge_national_parcels.py``.

    A row is now reported as the geometry it carries and nothing more. Unknown
    height, floors, ownership and FSI come back     null with the reason, because a
    null is answerable and an invented number is not.

    Gated behind the demo flag: the table is empty, and re-seeding it must not
    quietly repopulate a default deployment.
    """
    if not demo_mode_enabled():
        return None

    import json

    row = (await db.execute(
        text(
            """
            SELECT p.ulpin, p.survey_number, p.zonal_class, p.state_code,
                   p.district_code, p.boundary_code, p.area_m2,
                   p.derivation::text AS derivation_text,
                   ST_AsGeoJSON(p.geom) AS geom_json,
                   b.name AS locality_name
            FROM national_parcels p
            LEFT JOIN admin_boundaries b ON b.code = p.boundary_code
            WHERE p.ulpin = :ulpin
            """
        ),
        {"ulpin": ulpin},
    )).mappings().first()

    if row is None:
        return None

    derivation = None
    if row["derivation_text"]:
        try:
            derivation = json.loads(row["derivation_text"])
        except (TypeError, ValueError):
            derivation = None

    geometry = json.loads(row["geom_json"]) if row["geom_json"] else None
    # A generated parcel is retained only as modelled geometry for the 3D layer.
    authoritative = not (derivation or {}).get("authoritative", False)
    data_status = "geometry_only" if geometry else "record_without_geometry"

    return {
        "id": f"national-{row['ulpin']}",
        "ulpin": row["ulpin"],
        "survey_number": row["survey_number"],
        "polygon_geojson": geometry,
        "calculated_area_m2": float(row["area_m2"]) if row["area_m2"] is not None else None,
        "gis_area_m2": float(row["area_m2"]) if row["area_m2"] is not None else None,
        # There is no surveyed document behind this row, so no document area.
        "document_area_m2": None,
        "status": None,
        "data_status": data_status,
        "authoritative": authoritative,
        "derivation": derivation,
        "has_3d_twin": False,
        "location": {
            "state": row["state_code"],
            "state_code": row["state_code"],
            "district": row["district_code"],
            "district_code": row["district_code"],
            "boundary_code": row["boundary_code"],
            "locality": row["locality_name"],
        },
        "building": None,
        "fsi": {
            "plot_area_m2": float(row["area_m2"]) if row["area_m2"] is not None else None,
            "built_up_area_m2": None,
            "calculated_fsi": None,
            "max_allowed_fsi": None,
            "status": None,
            "status_reason": (
                "no permitted-FAR rule is available for this jurisdiction and no "
                "surveyed plot/built-up areas exist, so no FSI can be computed"
            ),
        },
        "levels": None,
        "units": None,
        "structures": None,
        "not_available": {
            "height_m": "no authoritative height source for this record",
            "floors": "no authoritative height source, so floors are not derivable",
            "ownership": "no public land-record or strata dataset exists for this parcel",
            "fsi": "withheld: a compliance verdict requires an authoritative FAR rule and surveyed inputs",
        },
    }


@router.get("/{ulpin}")
async def get_parcel_by_ulpin(ulpin: str, db: AsyncSession = Depends(get_db)):
    """Retrieves a specific parcel by 14-char ULPIN from the cadastral store."""
    await ensure_schema(db)
    u_clean = ulpin.strip().upper()

    parcel = (await db.execute(select(Parcel).where(Parcel.ulpin == ulpin))).scalar_one_or_none()
    if parcel is None:
        national = await _national_parcel_response(db, ulpin)
        if national is not None:
            return national
        # An unknown identifier is not an invitation to invent a building.
        # The previous fallback here synthesised a 6-floor, 24-unit parcel with
        # an "OWNERSHIP" right for a "Registered Allottee", a permitted-FAR
        # limit, fsi_status "PASS" and status "APPROVED" — for *any* ULPIN the
        # caller typed, at a hardcoded local coordinate, gated by nothing. A
        # fabricated title and a fabricated compliance verdict are the two
        # things this system must never emit.
        raise HTTPException(
            status_code=404,
            detail={
                "error": "no dataset ingested for this identifier",
                "ulpin": ulpin,
                "explanation": (
                    "No cadastral record exists for this identifier. Building "
                    "geometry is available for any area via POST /parcels/ingest-area "
                    "or GET /opendata/area, which resolve to published footprint data "
                    "(Microsoft GlobalML, OpenStreetMap) with real ground elevation."
                ),
                "not_available": [
                    "parcel boundary from a land-record source (no open bulk API)",
                    "floor ownership (no public dataset exists at this granularity)",
                    "FSI or any compliance verdict (requires an authoritative "
                    "permitted-FAR rule and surveyed inputs; neither is present)",
                ],
            },
        )

    structures = (
        await db.execute(
            select(Structure).where(Structure.parcel_id == parcel.id).options(selectinload(Structure.levels))
        )
    ).scalars().all()

    record_status = None
    review = None
    if structures:
        # The reviewer is the verification case's assigned verifier. Joining
        # users through sub.submitter_id reported the submitter's name as the
        # reviewer, which is the opposite of what this field claims to be.
        review = (
            await db.execute(text(
                """
                SELECT sub.receipt_number, sub.status, sub.declared_data,
                       vc.status AS decision, vc.officer_notes, vc.basis, vc.decision_timestamp,
                       COALESCE(rv.full_name, rv.username) AS reviewer_name,
                       COALESCE(su.full_name, su.username) AS submitted_by
                FROM submissions sub
                JOIN users su ON su.id = sub.submitter_id
                LEFT JOIN verification_cases vc ON vc.submission_id = sub.id
                LEFT JOIN users rv ON rv.id = vc.assigned_verifier_id
                WHERE sub.parcel_id = :pid
                ORDER BY sub.created_at DESC
                LIMIT 1
                """
            ), {"pid": parcel.id})
        ).mappings().first()
        if review:
            record_status = review["status"]

    structure_list = [
        {
            "building_code": s.building_code,
            "name": s.name,
            "height_m": s.height_m,
            "observed_height_m": s.observed_height_m,
            "floors_count": s.floors_count,
            "calculated_fsi": s.calculated_fsi,
            "extraction_source": s.extraction_source,
            "is_verified": bool(s.is_verified),
            "data_provenance": s.data_provenance,
            "height_basis": s.height_basis,
            "levels": [
                {
                    "level_code": lv.level_code,
                    "floor_number": lv.floor_number,
                    "min_z": lv.min_z,
                    "max_z": lv.max_z,
                    "level_type": lv.level_type,
                    "name": lv.name,
                    "use": lv.use,
                }
                for lv in (await db.execute(select(Level).where(Level.structure_id == s.id))).scalars().all()
            ],
        }
        for s in structures
    ]

    builder_record = None
    if review is not None:
        builder_record = {
            "receipt_number": review["receipt_number"],
            "status": review["status"],
            "declared_data": review["declared_data"],
            "decision": review["decision"] or None,
            "reviewer_name": review["reviewer_name"] or None,
            "submitted_by": review["submitted_by"] or None,
            "officer_notes": review["officer_notes"] or None,
            "basis": review["basis"] or None,
            "decision_timestamp": (
                review["decision_timestamp"].isoformat()
                if review["decision_timestamp"] is not None
                else None
            ),
        }

    return {
        "id": parcel.id,
        "ulpin": parcel.ulpin,
        "survey_number": parcel.survey_number,
        "polygon_geojson": parcel.polygon_geojson,
        "document_area_m2": parcel.document_area_m2,
        "calculated_area_m2": parcel.calculated_area_m2,
        "status": parcel.status,
        "has_3d_twin": bool(structure_list),
        "address": parcel.address,
        "locality": parcel.locality,
        "building": _building_of(
            structures[0] if structures else None,
            parcel=parcel,
            record_status=record_status,
        ),
        "builder_record": builder_record,
        "provenance": {
            "source": parcel.data_provenance,
            "authoritative": bool(parcel.provenance_authoritative),
            "detail": parcel.provenance_detail,
        },
        "levels": [],
        "units": [],
        "structures": structure_list,
    }

# --------------------------------------------------------------------------- #
# Ingestion from authentic sources
# --------------------------------------------------------------------------- #
def _ingested_ulpin(provider_tag: str, source_id: Any) -> str:
    """Stable synthetic key for a source footprint.

    These are not official ULPINs (only a land registry issues those), so the
    value is namespaced by provider and marked as such in ``data_provenance``.
    """
    import hashlib

    digest = hashlib.sha1(f"{provider_tag}:{source_id}".encode()).hexdigest().upper()
    return f"X-{provider_tag}-{digest[:10]}"[:14]


async def _ensure_ingest_jurisdiction(
    db: AsyncSession,
    lat: float,
    lon: float,
) -> Jurisdiction:
    """Jurisdiction row for ingested parcels.

    ``max_fsi`` is left NULL and ``provenance_authoritative`` False: a mapping
    source cannot supply a statutory FAR, so the FSI engine must withhold any
    compliance verdict for these parcels.
    """
    code = f"INGEST-{abs(lat):.2f}-{abs(lon):.2f}".replace(".", "")
    existing = (await db.execute(select(Jurisdiction).where(Jurisdiction.code == code))).scalar_one_or_none()
    if existing is not None:
        return existing
    row = Jurisdiction(
        id=code,
        code=code,
        name=f"Ingested area {lat:.4f}, {lon:.4f}",
        state="Unknown (from source footprint)",
        district="Unknown",
        taluka="Unknown",
        village_ward=f"r{int(500)}m window",
        center_lat=lat,
        center_lng=lon,
        max_fsi=None,
        provenance_authoritative=False,
        rule_source=None,
    )
    db.add(row)
    await db.commit()
    return row


@router.post("/ingest-area")
async def ingest_area(
    lat: float = Query(..., description="Centre latitude (WGS84)"),
    lon: float = Query(..., description="Centre longitude (WGS84)"),
    radius: int = Query(500, ge=100, le=1500),
    limit: int = Query(25, ge=1, le=200, description="Max footprints to ingest"),
    jurisdiction_code: Optional[str] = Query(None, description="Existing jurisdiction to attach to"),
    db: AsyncSession = Depends(get_db),
):
    """Ingest real building footprints for an area as cadastral parcels.

    Geometry comes from the configured providers in ``app.sources``. Each parcel
    records its provenance; no permitted-FSI rule is invented, so FSI verdicts
    stay withheld until an authoritative jurisdiction record is supplied.
    """
    await ensure_schema(db)
    try:
        area_data = await _run_in_thread(lat, lon, radius, limit)
    except NoAuthenticSourceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    prov = area_data.provenance
    tag = {"openstreetmap": "OSM", "data.gov.in": "OGD", "bhuvan": "BHV"}.get(prov.provider, "SRC")

    if jurisdiction_code:
        jur = (await db.execute(select(Jurisdiction).where(Jurisdiction.code == jurisdiction_code))).scalar_one_or_none()
        if jur is None:
            raise HTTPException(status_code=404, detail=f"unknown jurisdiction_code {jurisdiction_code}")
    else:
        jur = await _ensure_ingest_jurisdiction(db, lat, lon)

    created, updated = [], []
    for b in area_data.buildings[:limit]:
        ring = b["ring_geo"]
        geojson = {"type": "Polygon", "coordinates": [[[float(x), float(y)] for x, y in ring]]}
        area_m2 = float(b.get("footprint_area_m2") or 0.0)
        ulpin = _ingested_ulpin(tag, b["id"])
        existing = (await db.execute(select(Parcel).where(Parcel.ulpin == ulpin))).scalar_one_or_none()
        parcel = await upsert_parcel(
            db,
            ulpin=ulpin,
            survey_number=f"{tag}-{b['id']}",
            jurisdiction_id=jur.id,
            polygon_wkt_2d=polygon_wkt(ring),
            polygon_geojson=geojson,
            document_area_m2=area_m2,
            calculated_area_m2=area_m2,
            status="SURVEYED",
        )
        parcel.data_provenance = prov.provider
        parcel.provenance_authoritative = prov.authoritative
        parcel.provenance_detail = {
            **prov.as_dict(),
            "source_id": b["id"],
            "height_basis": "source" if b.get("height_m") else "unknown",
        }
        await db.commit()

        st = (await db.execute(select(Structure).where(Structure.parcel_id == parcel.id))).scalars().first()
        if st is None:
            st = Structure(
                parcel_id=parcel.id,
                building_code=f"{tag}-{b['id']}",
                name=str(b.get("name") or f"{tag} footprint {b['id']}")[:200],
                structure_type=str(b.get("type") or "UNSPECIFIED")[:50],
                footprint_geojson=geojson,
                height_m=float(b.get("height_m") or 0.0),
                floors_count=int(b.get("floors") or 0),
                total_built_up_area_m2=area_m2 * int(b.get("floors") or 0),
                calculated_fsi=None,
                data_provenance=prov.provider,
                provenance_authoritative=prov.authoritative,
                height_basis="source" if b.get("height_m") else "unknown",
                extraction_source=f"{prov.provider}:{prov.dataset}",
            )
            db.add(st)
        else:
            st.footprint_geojson = geojson
            st.height_m = float(b.get("height_m") or st.height_m or 0.0)
            st.data_provenance = prov.provider
            st.provenance_authoritative = prov.authoritative
        await db.commit()
        (created if existing is None else updated).append(ulpin)

    return {
        "ingested": len(created) + len(updated),
        "created": len(created),
        "updated": len(updated),
        "ulpins": created + updated,
        "jurisdiction": {"code": jur.code, "max_fsi": jur.max_fsi, "provenance_authoritative": jur.provenance_authoritative},
        "provenance": prov.as_dict(),
        "warnings": area_data.warnings,
        "note": "Permitted FSI is not set for ingested footprints, so FSI verdicts are withheld (RULE_UNAVAILABLE).",
    }


async def _run_in_thread(lat: float, lon: float, radius: int, limit: int):
    """Run the blocking provider fetch off the event loop."""
    from fastapi.concurrency import run_in_threadpool

    from app.sources import fetch_area

    return await run_in_threadpool(fetch_area, lat, lon, radius, limit)
