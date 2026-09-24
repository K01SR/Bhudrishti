from typing import Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Response, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles, TokenPayload, RoleEnum

from app.id_engine.generator import (
    generate_proposed_3d_id,
    parse_and_validate_3d_id,
    explain_id_specification,
    calculate_luhn_mod36_checksum,
)
from app.id_engine.types import (
    SpatialTypeCode,
    SPATIAL_TYPE_DESCRIPTIONS,
    SPECIFICATION_LABEL,
    SPECIFICATION_DISCLAIMER,
)
from app.id_engine.national import (
    NATIONAL_ULPIN_SPEC,
    parcel_ulpin_from_vertices,
    national_ulpin_for_local_ring,
    verify_parcel_ulpin,
    verify_local_ring,
    local_to_latlon,
)

router = APIRouter(prefix="/ids", tags=["Proposed 3D ULPIN Extension"])

MINT_OPERATOR = require_roles([RoleEnum.DISTRICT_VERIFIER, RoleEnum.TALUKA_VERIFIER, RoleEnum.STATE_ADMIN])


class GenerateIDRequest(BaseModel):
    parent_ulpin: str = Field(..., min_length=14, max_length=14, example="12345678901234")
    type_code: SpatialTypeCode = Field(..., example="U")
    building_code: str = Field(..., example="B17")
    level_code: str = Field(..., example="L05")
    unit_code: str = Field(..., example="501")


class NationalUlpinRequest(BaseModel):
    ring: list = Field(..., description="Parcel ring. Geo-referenced [lat, lon] pairs (or meter pairs when origin supplied).")
    ulpin: Optional[str] = Field(None, description="ULPIN to verify against the ring (used by /verify).")
    origin_easting: Optional[float] = Field(None, description="UTM easting origin of the local cadastral frame (fallback airoli origin).")
    origin_northing: Optional[float] = Field(None, description="UTM northing origin of the local cadastral frame.")
    utm_zone: int = Field(43, description="UTM zone for EPSG:326NN local->WGS84 conversion.")


@router.get("/specification")
def get_specification_guide():
    """Returns official technical documentation of the Proposed Bhu-Drishti 3D ID Scheme."""
    return explain_id_specification()


@router.post("/generate")
def generate_id(req: GenerateIDRequest):
    """
    Generates a deterministic Proposed 3D ID with Luhn Mod 36 Checksum:
    {parent_14_char_ULPIN}/{TYPE}{BUILDING}-{LEVEL}-{UNIT}-{CHECK}
    """
    try:
        generated_id = generate_proposed_3d_id(
            parent_ulpin=req.parent_ulpin,
            type_code=req.type_code.value,
            building_code=req.building_code,
            level_code=req.level_code,
            unit_code=req.unit_code,
        )
        return {
            "proposed_3d_id": generated_id,
            "specification": SPECIFICATION_LABEL,
            "disclaimer": SPECIFICATION_DISCLAIMER,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/decode")
def decode_id(id_string: str = Query(..., description="Full 3D ID, e.g. 12345678901234/UB17-L05-501-W")):
    """
    Parses and cryptographically validates syntax and check digit for an ID.
    Returns semantic domain breakdown and checksum calculation trace.
    """
    parsed = parse_and_validate_3d_id(id_string)
    
    # Calculate checksum steps for UI explanation
    cleaned_body = "".join(c.upper() for c in id_string[:-1] if c.isalnum())
    computed_check = calculate_luhn_mod36_checksum(id_string[:-1]) if len(id_string) > 2 else "0"

    return {
        "raw_input": parsed.raw_id,
        "is_valid": parsed.is_valid,
        "validation_message": parsed.validation_message,
        "specification": parsed.specification,
        "parsed_components": {
            "parent_14_char_ulpin": parsed.parent_ulpin,
            "type_code": parsed.type_code.value if hasattr(parsed.type_code, "value") else str(parsed.type_code),
            "type_description": parsed.type_description,
            "building_code": parsed.building_code,
            "level_code": parsed.level_code,
            "unit_code": parsed.unit_code,
            "checksum_character": parsed.checksum,
        },
        "checksum_verification": {
            "algorithm": "ISO/IEC 7064 Alphanumeric Luhn Mod 36",
            "computed_check_digit": computed_check,
            "received_check_digit": parsed.checksum,
            "matches": parsed.is_valid,
        },
    }


@router.get("/national-ulpin/spec")
def get_national_ulpin_spec():
    """Returns the documented national ULPIN (Bhu-Aadhaar) alignment reference."""
    return {
        "national_ulpin": NATIONAL_ULPIN_SPEC,
        "alignment": (
            "Every 3D identifier's parent segment is a 14-char ULPIN derived from "
            "georeferenced parcel vertices. See docs/04-id-spec.md section 3."
        ),
    }


@router.post("/national-ulpin/derive")
def derive_national_ulpin(req: NationalUlpinRequest):
    """
    Derives a deterministic 14-character national-style parcel ULPIN from parcel
    vertices. Pass geo-referenced [lat, lon] pairs directly, OR metre pairs of the
    local cadastral frame together with the UTM origin (defaults to the documented
    Airoli origin) — the module converts to WGS84 before derivation.
    """
    AIROLI_DEFAULT = {"easting": 298000.0, "northing": 2113500.0}
    try:
        if req.origin_easting is not None and req.origin_northing is not None:
            ulpin, meta = national_ulpin_for_local_ring(
                req.ring,
                origin_easting=req.origin_easting,
                origin_northing=req.origin_northing,
                utm_zone=req.utm_zone,
            )
        else:
            ulpin, meta = parcel_ulpin_from_vertices(req.ring)
        meta["example_origin_if_local"] = AIROLI_DEFAULT
        return {
            "ulpin": ulpin,
            "length": len(ulpin),
            "derivation": meta,
            "disclaimer": (
                "Deterministic national-aligned derivation for offline evaluation. "
                "Production must consume the official DOLR/state ULPIN API."
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/national-ulpin/verify")
def verify_national_ulpin(req: NationalUlpinRequest):
    """
    Verifies a national-style ULPIN against its parcel vertices (same input rules
    as /derive). Returns boolean validity plus human-readable message.
    """
    AIROLI_DEFAULT = {"easting": 298000.0, "northing": 2113500.0}
    try:
        if req.origin_easting is not None and req.origin_northing is not None:
            ok, message = verify_local_ring(
                req.ulpin or "",
                req.ring,
                origin_easting=req.origin_easting,
                origin_northing=req.origin_northing,
                utm_zone=req.utm_zone,
            )
        else:
            ok, message = verify_parcel_ulpin(req.ulpin or "", req.ring)
        return {
            "valid": ok,
            "message": message,
            "probe_ulpin": req.ulpin,
            "disclaimer": NATIONAL_ULPIN_SPEC["official_api_note"],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Phase 2: engine-first national ULPIN layer on real DB parcels
# ---------------------------------------------------------------------------

class BoundaryULPINRequest(BaseModel):
    boundary_code: str = Field(..., description="Code of a real admin boundary (VILLAGE/TALUKA/DISTRICT/STATE).")
    limit: int = Field(50, ge=1, le=500)


@router.get("/national-ulpin/parcels")
def get_national_ulpins_for_boundary(
    boundary_code: str = Query(..., description="Real admin boundary code, e.g. 'MH-AHMADNAGAR-NAGAR-1'"),
    limit: int = Query(50, ge=1, le=500),
    synthesize: bool = Query(True, description="Synthesize parcel grid inside the boundary if none exist yet."),
):
    """
    Phase 2 - Engine-first: returns ULPINs for real parcels inside a real
    admin boundary (village/taluka/district/state). If the boundary has no
    parcels yet and ``synthesize=true``, deterministically synthesises a parcel
    grid clipped to the real administrative polygon and derives each parcel's
    14-char ULPIN from its georeferenced lat/lon vertices.
    """
    from app.pipelines.national_parcels import (
        ensure_parcels_for_village,
        synthesize_parcels_for_boundary,
        list_synthesized_parcels,
    )
    from app.core.demo_gate import require_demo_mode

    require_demo_mode("Synthesized National Parcels")

    from app.core.database import SyncSessionLocal

    with SyncSessionLocal() as db:
        if synthesize:
            ensure_parcels_for_village(db, boundary_code)
        parcels = list_synthesized_parcels(db, boundary_code, limit=limit)

    return {
        "boundary_code": boundary_code,
        "total_parcels": len(parcels),
        "parcels": parcels,
        "note": (
            "Parcels are deterministic synthetic subdivisions of the real administrative "
            "polygon; ULPINs derive from georeferenced vertices (Bhu-Aadhaar aligned). "
            "Production issuance must use the official DOLR/state ULPIN API."
        ),
    }


@router.post("/national-ulpin/derive-boundary")
def derive_ulpins_for_boundary(req: BoundaryULPINRequest):
    """
    Phase 2 - Engine-first: forces (re)synthesis + ULPIN derivation for every
    parcel inside a real boundary. Idempotent (upserts by derived ULPIN).
    """
    from app.core.demo_gate import require_demo_mode

    require_demo_mode("National Boundary ULPIN Derivation")

    from app.pipelines.national_parcels import synthesize_parcels_for_boundary
    from app.core.database import SyncSessionLocal

    with SyncSessionLocal() as db:
        result = synthesize_parcels_for_boundary(db, req.boundary_code)
    return result


@router.post("/national-ulpin/verify-parcel")
def verify_national_parcel_ulpin(
    ulpin: str = Query(..., description="The 14-char national ULPIN to verify."),
):
    """
    Phase 2 - Engine-first: verifies a stored national parcel ULPIN against the
    known DB parcel: re-derives from its geometry and re-checks the Luhn Mod-36
    checksum. Returns the verification trace plus the stored parcel context.
    """
    from app.core.demo_gate import require_demo_mode

    require_demo_mode("Stored National Parcel Verification")

    from app.core.database import SyncSessionLocal
    from app.models.national_parcel import NationalParcel
    from app.id_engine.national import verify_parcel_ulpin

    with SyncSessionLocal() as db:
        row = db.execute(
            select(NationalParcel).where(NationalParcel.ulpin == ulpin.upper())
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail=f"No national parcel with ULPIN '{ulpin}'.")
        ring = []
        if row.geom is not None:
            from geoalchemy2.shape import to_shape
            g = to_shape(row.geom)
            ring = [(pt[1], pt[0]) for pt in list(g.exterior.coords)[:-1]]
        ok, message = verify_parcel_ulpin(row.ulpin, ring)
        return {
            "valid": ok,
            "message": message,
            "ulpin": row.ulpin,
            "survey_number": row.survey_number,
            "boundary_code": row.boundary_code,
            "centroid_lat": row.centroid_lat,
            "centroid_lng": row.centroid_lng,
            "area_m2": row.area_m2,
            "zonal_class": row.zonal_class,
            "checksum_verified": ok,
        }


@router.get("/precinct")
def get_all_precinct_3d_ids():
    """
    Returns full catalogue of all 3D ULPINs generated across the entire precinct,
    including hero building B-17 and all 12 precinct buildings (B-01 to B-12).
    """
    from app.api.v1.precinct import _precinct_buildings_payload
    buildings = _precinct_buildings_payload()
    result = []
    total_units = 0

    for b in buildings:
        b_units = []
        for u in b.get("units", []):
            b_units.append({
                "unit_number": u.get("unit_number"),
                "proposed_3d_id": u.get("proposed_3d_id"),
                "level_code": u.get("level_code"),
                "unit_type": u.get("unit_type"),
                "min_z": u.get("min_z"),
                "max_z": u.get("max_z"),
                "carpet_area_m2": u.get("carpet_area_m2"),
                "built_up_area_m2": u.get("built_up_area_m2"),
            })
            total_units += 1

        result.append({
            "code": b.get("code"),
            "name": b.get("name"),
            "type": b.get("type"),
            "floors": b.get("floors"),
            "height_m": b.get("height_m"),
            "parent_ulpin": b.get("ulpin"),
            "building_3d_id": b.get("proposed_3d_id"),
            "status": b.get("status"),
            "units_count": len(b_units),
            "units": b_units,
        })

    return {
        "specification": SPECIFICATION_LABEL,
        "total_buildings": len(result),
        "total_3d_ids": total_units,
        "buildings": result,
    }


@router.get("/building/{building_code}")
def get_building_3d_ids(building_code: str):
    """Returns all 3D ULPINs for a specific building with validation trace."""
    from app.api.v1.precinct import get_precinct_building_by_code
    b = get_precinct_building_by_code(building_code)
    units_with_validation = []
    for u in b.get("units", []):
        parsed = parse_and_validate_3d_id(u["proposed_3d_id"])
        units_with_validation.append({
            "unit_number": u.get("unit_number"),
            "proposed_3d_id": u.get("proposed_3d_id"),
            "level_code": u.get("level_code"),
            "unit_type": u.get("unit_type"),
            "min_z": u.get("min_z"),
            "max_z": u.get("max_z"),
            "carpet_area_m2": u.get("carpet_area_m2"),
            "is_valid": parsed.is_valid,
            "checksum": parsed.checksum,
        })

    return {
        "code": b.get("code"),
        "name": b.get("name"),
        "parent_ulpin": b.get("ulpin"),
        "building_3d_id": b.get("proposed_3d_id"),
        "units_count": len(units_with_validation),
        "units": units_with_validation,
    }


@router.get("/resolve")
async def resolve_identifier(
    identifier: str = Query(
        ...,
        description=(
            "Any identifier the UI can be holding: a bare parcel ULPIN "
            "('12345678901234'), a canonical 3D unit ID "
            "('12345678901234/UB17-L05-501-W'), or a precinct building code "
            "('UB17'). Resolves to the parcel, and to the structure/level/unit "
            "when the identifier names one."
        ),
    ),
    db: AsyncSession = Depends(get_db),
):
    """Resolve one identifier to a route, whether or not a record exists.

    Selection and deep links both need the same answer to "what is this, and
    where does it live", and until now they asked different questions of
    different endpoints: ``/ids/decode`` reported whether a string was
    *syntactically* a 3D ID, ``/parcels/{ulpin}`` looked up a parcel, and a
    canonical 3D ID could not be sent to the parcel route at all - its ``/`` is
    a path separator, so ``/parcels/12345678901234/UB17-L05-501-W`` matched no
    route and answered a bare ``{"detail": "Not Found"}``. The UI mints exactly
    that form (PropertyDetail builds ``property_id`` as ``{ulpin}/{code}``), so
    the product could produce an identifier it was unable to resolve.

    A valid checksum is a claim about syntax, not about existence, so this
    reports the two separately: ``identifier_valid`` says the string is
    well-formed, ``exists`` says whether the cadastral store holds it. Nothing
    here invents a record - an unresolvable identifier is a 404 that explains
    what was looked for and where real geometry does come from.
    """
    from app.core.cadastre_store import ensure_schema
    from app.models.cadastre import Level, Parcel, Structure, Unit

    raw = identifier.strip()
    await ensure_schema(db)

    parsed = None
    parent_ulpin = raw.upper()
    building_code = None
    level_code = None
    unit_code = None

    if "/" in raw:
        head, _, tail = raw.partition("/")
        parent_ulpin = head.strip().upper()
        tail = tail.strip().upper()
        try:
            parsed = parse_and_validate_3d_id(raw)
        except Exception:  # noqa: BLE001 - an unparseable tail is still resolvable as a parcel
            parsed = None
        if parsed is not None:
            building_code = parsed.building_code or None
            level_code = parsed.level_code or None
            unit_code = parsed.unit_code or None
        else:
            building_code = level_code = unit_code = None
        if not building_code and tail:
            # The parser yields empty components rather than raising when the
            # parent is not a 14-char ULPIN - which is the normal case for a
            # parcel derived from published footprints, since those carry a
            # source-scoped ID. Keep the raw tail so the lookup and the
            # "unresolved" message still name the thing that was asked for,
            # rather than reporting an empty building code.
            building_code = tail

    row = (
        await db.execute(select(Parcel).where(Parcel.ulpin == parent_ulpin))
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "no dataset ingested for this identifier",
                "identifier": raw,
                "parent_ulpin": parent_ulpin,
                # None, not False, for a bare parcel ID: there is no syntax
                # validator for one, and reporting it invalid would be a claim
                # nobody checked. Only the 3D ID form has a check digit to test.
                "identifier_valid": bool(parsed.is_valid) if parsed is not None else None,
                "explanation": (
                    f"No cadastral record exists for {parent_ulpin}. Building geometry is "
                    "available for any area via POST /parcels/ingest-area or "
                    "GET /opendata/area, which resolve to published footprint data "
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

    structure = None
    if building_code:
        structure = (
            await db.execute(
                select(Structure).where(
                    Structure.parcel_id == row.id,
                    Structure.building_code == building_code,
                )
            )
        ).scalar_one_or_none()

    level = None
    if structure is not None and level_code:
        level = (
            await db.execute(
                select(Level).where(
                    Level.structure_id == structure.id,
                    Level.level_code == level_code,
                )
            )
        ).scalar_one_or_none()

    unit = None
    if level is not None and unit_code:
        unit = (
            await db.execute(
                select(Unit).where(
                    Unit.level_id == level.id,
                    Unit.unit_number == unit_code,
                )
            )
        ).scalar_one_or_none()
    unit_exists = unit is not None if unit_code else None

    # A well-formed ID whose structure was never ingested resolves to the
    # parcel and says so, rather than 404-ing a link that a human can follow.
    exists = row is not None and (building_code is None or structure is not None)

    return {
        "identifier": raw,
        "identifier_valid": bool(parsed and parsed.is_valid) if parsed else None,
        "exists": exists,
        "parent_ulpin": parent_ulpin,
        "route": f"/app/properties/{parent_ulpin}"
        + (f"?unit={building_code}" if building_code else ""),
        "parsed_components": {
            "building_code": building_code,
            "level_code": level_code,
            "unit_code": unit_code,
        } if parsed else None,
        "parcel": {
            "ulpin": row.ulpin,
            "address": row.address,
            "locality": row.locality,
            "status": row.status,
            "data_provenance": row.data_provenance,
            "provenance_authoritative": bool(row.provenance_authoritative),
            "geometry_present": bool(row.polygon_geojson or row.boundary_coordinates),
        },
        "structure": (
            {
                "building_code": structure.building_code,
                "name": structure.name,
                "structure_type": structure.structure_type,
            }
            if structure is not None
            else None
        ),
        "level": (
            {
                "level_code": level.level_code,
                "floor_number": level.floor_number,
                "level_type": level.level_type,
            }
            if level is not None
            else None
        ),
        "unit": (
            {
                "unit_number": unit.unit_number,
                "proposed_3d_id": unit.proposed_3d_id,
                "unit_type": unit.unit_type,
                "carpet_area_m2": unit.carpet_area_m2,
            }
            if unit is not None
            else None
        ),
        "unit_exists": unit_exists,
        "unresolved": (
            None
            if exists
            else {
                "building_code": building_code,
                "reason": "no structure with that building code is ingested for this parcel",
            }
        ),
    }


@router.get("/unextruded-parcels")
def list_unextruded_2d_parcels():
    """
    Returns all 2D cadastre parcels that currently lack a 3D digital twin or 3D-ULPIN units.
    Provides suggested building typology, floors, and permissible FSI for auto-extrusion.
    """
    from app.id_engine.extruder import get_unextruded_parcels
    parcels = get_unextruded_parcels()
    return {
        "total_unextruded": len(parcels),
        "parcels": parcels,
        "action": "Call POST /api/v1/ids/extrude-all-2d to automatically mint 3D-ULPINs for all parcels.",
    }


@router.post("/extrude-all-2d")
def extrude_all_2d_parcels(_auth: TokenPayload = Depends(MINT_OPERATOR)):
    """
    Batch AI Extrusion Pipeline:
    Converts ALL 2D cadastre parcels lacking 3D digital twins into fully stratified 3D models.
    Mints ISO/IEC 7064 Luhn Mod 36 compliant 3D-ULPINs for every level, unit, parking slot,
    subsurface utility, and rooftop air-rights column.
    """
    from app.id_engine.extruder import extrude_all_unextruded_parcels
    return extrude_all_unextruded_parcels()


class ExtrudeSingleRequest(BaseModel):
    building_name: Optional[str] = None
    building_code: Optional[str] = None
    typology: Optional[str] = None
    floors: Optional[int] = None
    units_per_floor: Optional[int] = None


@router.post("/extrude-parcel/{ulpin}")
def extrude_single_2d_parcel(ulpin: str, req: Optional[ExtrudeSingleRequest] = None, _auth: TokenPayload = Depends(MINT_OPERATOR)):
    """
    Extrudes an individual 2D parcel into a 3D digital twin on demand,
    minting verified 3D-ULPINs for all strata units.
    """
    from app.id_engine.extruder import extrude_single_parcel
    custom = {}
    if req:
        if req.building_name:
            custom["name"] = req.building_name
        if req.building_code:
            custom["code"] = req.building_code
        if req.typology:
            custom["type"] = req.typology
        if req.floors:
            custom["floors"] = req.floors
        if req.units_per_floor:
            custom["units_per_floor"] = req.units_per_floor
    try:
        return extrude_single_parcel(ulpin=ulpin, custom_params=custom)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Phase 3: persisted national 3D twins (real georeferenced geometry + NBC setbacks)
# ---------------------------------------------------------------------------

class NationalTwinRequest(BaseModel):
    boundary_code: str = Field(..., description="Admin boundary code containing national parcels to extrude.")
    limit: int = Field(50, ge=1, le=500)
    force: bool = Field(False, description="Re-extrude existing twins.")


@router.post("/national-twin/extrude-parcel/{ulpin}")
def extrude_national_twin_for_parcel(ulpin: str, req: Optional[ExtrudeSingleRequest] = None, _auth: TokenPayload = Depends(MINT_OPERATOR)):
    """
    Phase 3 - Persisted twin: extrudes ONE national parcel (real EPSG:4326
    geometry, own UTM zone, NBC 2016 setback) into a persisted 3D twin.
    """
    from app.core.demo_gate import require_demo_mode
    require_demo_mode("National Twin Extrusion")
    from app.pipelines.national_twins import extrude_national_parcel
    from app.core.database import SyncSessionLocal

    custom = {}
    if req:
        if req.building_name:
            custom["name"] = req.building_name
        if req.building_code:
            custom["code"] = req.building_code
        if req.typology:
            custom["type"] = req.typology
        if req.floors:
            custom["floors"] = req.floors
        if req.units_per_floor:
            custom["units_per_floor"] = req.units_per_floor
    try:
        with SyncSessionLocal() as db:
            return extrude_national_parcel(db, ulpin, custom_params=custom or None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/national-twin/extrude-boundary")
def extrude_national_twins_for_boundary(req: NationalTwinRequest, _auth: TokenPayload = Depends(MINT_OPERATOR)):
    """
    Phase 3 - Persisted twin: extrudes all national parcels inside a boundary
    into persisted 3D twins (idempotent; skip when already extruded unless force).
    """
    from app.core.demo_gate import require_demo_mode
    require_demo_mode("National Twin Extrusion")
    from app.pipelines.national_twins import extrude_parcels_for_boundary
    from app.core.database import SyncSessionLocal

    with SyncSessionLocal() as db:
        return extrude_parcels_for_boundary(db, req.boundary_code, limit=req.limit, force=req.force)


@router.get("/national-twin/{ulpin}")
def get_national_twin(ulpin: str):
    """
    Phase 3 - Persisted twin: returns the persisted 3D twin for a national parcel.
    """
    from app.core.demo_gate import require_demo_mode
    require_demo_mode("Persisted National 3D Twin")
    from app.pipelines.national_twins import get_twin_detail
    from app.core.database import SyncSessionLocal

    with SyncSessionLocal() as db:
        detail = get_twin_detail(db, ulpin)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No persisted twin for ULPIN '{ulpin}'.")
    return detail


@router.get("/template/excel")
def download_excel_template():
    """
    Downloads an official Excel workbook (.xlsx) template with column definitions,
    validations, and pre-filled sample data for 3D ULPIN extrusion.
    """
    from app.id_engine.spreadsheet_importer import generate_sample_excel_template
    excel_bytes = generate_sample_excel_template()
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Bhu_Drishti_3D_ULPIN_Template.xlsx"}
    )


@router.get("/template/csv")
def download_csv_template():
    """Downloads a CSV template for 3D ULPIN batch building upload."""
    from app.id_engine.spreadsheet_importer import generate_sample_csv_template
    csv_str = generate_sample_csv_template()
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=Bhu_Drishti_3D_ULPIN_Template.csv"}
    )


@router.post("/generate-from-spreadsheet")
async def generate_3d_ulpins_from_spreadsheet(file: UploadFile = File(...), _auth: TokenPayload = Depends(MINT_OPERATOR)):
    """
    Upload an Excel (.xlsx) or CSV file containing building and unit geometry specs.
    Automatically stratifies and extrudes 3D digital twin models, mints Luhn Mod 36 3D-ULPINs,
    calculates FSI and built-up areas, and stages records into the Cadastral Blockchain!
    """
    from app.id_engine.spreadsheet_importer import parse_and_extrude_spreadsheet
    filename = file.filename or "upload.xlsx"
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    try:
        result = parse_and_extrude_spreadsheet(contents, filename)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Spreadsheet parsing error: {str(e)}")
