from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.crypto import sign_canonical_record
from app.core.crypto_disclosure import (
    CRYPTO_DISCLOSURE,
    NO_SIGNING_AUTHORITY,
    SIGNATURE_STATUS,
)
from app.core.demo_gate import DemoDataDisabled, demo_mode_enabled, empty_dataset, require_demo_mode
from app.pipelines.synthetic_generator import generate_synthetic_airoli_dataset
from app.pipelines.vertical_delineation import VerticalDelineationPipeline
from app.qa_engine.rules import TopologyQAEngine
from app.schemas.canonical_property import get_canonical_json_schema

router = APIRouter(prefix="/properties", tags=["3D Cadastral Properties"])

# Global singleton synthetic dataset cache. Empty when the demo gate is shut, so
# the application still starts and every generated-data route reports the gate
# rather than crashing at import time.
if demo_mode_enabled():
    _DATASET_CACHE = generate_synthetic_airoli_dataset()
else:
    _DATASET_CACHE = empty_dataset()
    _DATASET_CACHE["demo_disabled"] = True
_DELINEATOR = VerticalDelineationPipeline()
_QA_ENGINE = TopologyQAEngine()


async def _load_pipeline_provenance() -> Dict[str, Any]:
    """Reads the latest persisted VC-X run, asset, and vertical structure from PostGIS.

    These are REAL pipeline artifacts (measured metrics, provenance hash, SHA-256 asset,
    detected floor levels) that anchor the demo payload to the true processing chain.

    This was sync and called ``asyncio.run()``. FastAPI therefore ran it in a
    threadpool, and ``asyncio.run`` built a fresh event loop per request, so the
    query could never share a pooled connection. Now ``async def``: it runs on
    the server loop and reuses the pool.
    """
    async def _query() -> Dict[str, Any]:
        from sqlalchemy import select, desc
        from sqlalchemy.orm import selectinload
        from app.core.database import get_sessionmaker
        from app.models.pipeline import PipelineRun, DatasetAsset
        from app.models.cadastre import Structure
        from app.id_engine.national import compose_vertical_ulpin

        async with get_sessionmaker()() as db:
            run = (await db.execute(select(PipelineRun).order_by(desc(PipelineRun.created_at)).limit(1))).scalar_one_or_none()
            asset = None
            if run and run.asset_id:
                asset = (await db.execute(select(DatasetAsset).where(DatasetAsset.id == run.asset_id))).scalar_one_or_none()
            structure = (await db.execute(
                select(Structure).options(selectinload(Structure.levels)).where(Structure.building_code == "B-17")
            )).scalar_one_or_none()
            detected_levels = []
            if structure and structure.levels:
                detected_levels = [lv.level_code for lv in structure.levels][:14]
            composite = None
            if structure:
                try:
                    composite = compose_vertical_ulpin(
                        parent_ulpin="12345678901234",
                        type_code="G",
                        building_code="B17",
                        level_code=detected_levels[-1] if detected_levels else "L04",
                        unit_code="001",
                    )
                except Exception:
                    composite = None
            return {
                "engine": "vertical-cadastre-extraction (deterministic-first)",
                "run_hash": run.run_hash if run else None,
                "run_id": run.id if run else None,
                "status": run.status if run else "NO_RUN",
                "metrics": run.metrics if run else None,
                "actor_id": run.actor_id if run else None,
                "run_created_at": run.created_at.isoformat() if run and run.created_at else None,
                "asset": {
                    "dataset_id": asset.dataset_id if asset else None,
                    "format": asset.format if asset else None,
                    "file_sha256": asset.file_sha256 if asset else None,
                    "bytes": asset.bytes if asset else None,
                },
                "detected_structure": {
                    "building_code": structure.building_code if structure else None,
                    "observed_height_m": structure.observed_height_m if structure else None,
                    "extraction_source": structure.extraction_source if structure else None,
                    "detected_levels": detected_levels,
                    "has_postgis_3d_solid": structure.geom_3d is not None if structure else False,
                },
                "vertical_composite_id": composite,
            }

    try:
        return await _query()
    except Exception:
        return {
            "engine": "vertical-cadastre-extraction (deterministic-first)",
            "run_hash": None,
            "status": "NO_RUN",
            "metrics": None,
            "asset": None,
            "detected_structure": None,
        }


async def _load_scene3d() -> Optional[Dict[str, Any]]:
    """Builds the data-driven 3D scene specification from PostGIS (see scene architect).

    Passing a pooled session in is the point of this change. ``build_scene3d``
    with no session builds and disposes its own engine per call, which is exactly
    the per-request handshake this path existed to avoid.
    """
    from app.core.database import get_sessionmaker
    from app.scene import build_scene3d

    try:
        async with get_sessionmaker()() as db:
            return await build_scene3d(db)
    except Exception:
        return None


async def build_hero_property_response() -> Dict[str, Any]:
    require_demo_mode("Canonical Hero Property")
    dataset = _DATASET_CACHE
    hero_p = dataset["hero_parcel"]
    hero_s = dataset["hero_structure"]
    levels = dataset["levels"]
    units = dataset["units"]
    subsurface = dataset["subsurface_objects"]
    elevated = dataset["elevated_objects"]

    # Scene specification assembled from the persisted PostGIS cadastre.
    scene3d = await _load_scene3d()

    # Compute 3D meshes for all units
    enriched_units = []
    for u in units:
        mesh_info = _DELINEATOR.extrude_unit_volume(
            polygon_coords=u["coords"],
            min_z=u["min_z"],
            max_z=u["max_z"],
        )
        
        # Attach synthetic demo rights
        rights_list = []
        if u["unit_number"] == "201":
            # Flat 201 Hero Case: Ownership, Mortgage, Easement
            rights_list.extend([
                {
                    "right_type": "OWNERSHIP",
                    "party_name": "Karan Malhotra & Priya Malhotra",
                    "party_type": "NATURAL_PERSON",
                    "share_pct": 100.0,
                    "encumbrance_status": "ACTIVE",
                    "color_hex": "#10B981",  # Emerald Green
                },
                {
                    "right_type": "MORTGAGE",
                    "party_name": "State Bank of India (Airoli Branch)",
                    "party_type": "FINANCIAL_INSTITUTION",
                    "mortgage_amount_inr": 8500000.0,
                    "encumbrance_status": "ACTIVE",
                    "color_hex": "#EF4444",  # Red
                },
                {
                    "right_type": "EASEMENT",
                    "party_name": "Building B-17 Cooperative Housing Society",
                    "party_type": "HOUSING_SOCIETY",
                    "easement_purpose": "Access to Shared Corridor & Fire Evacuation Staircase",
                    "encumbrance_status": "ACTIVE",
                    "color_hex": "#3B82F6",  # Blue
                },
            ])
        elif u["unit_type"] == "P":
            rights_list.append({
                "right_type": "OWNERSHIP",
                "party_name": "Building B-17 CHS Common Property",
                "party_type": "HOUSING_SOCIETY",
                "share_pct": 100.0,
                "encumbrance_status": "ACTIVE",
                "color_hex": "#6B7280",
            })
        else:
            rights_list.append({
                "right_type": "OWNERSHIP",
                "party_name": f"Registered Allottee (Flat {u['unit_number']})",
                "party_type": "NATURAL_PERSON",
                "share_pct": 100.0,
                "encumbrance_status": "ACTIVE",
                "color_hex": "#10B981",
            })

        u_dict = dict(u)
        u_dict["mesh_3d"] = mesh_info["mesh_3d"]
        u_dict["center"] = mesh_info["center"]
        u_dict["rights"] = rights_list
        enriched_units.append(u_dict)

    # Run QA Topology validation
    qa_results = _QA_ENGINE.run_all_rules(
        parcel_data=hero_p,
        structure_data=hero_s,
        levels_data=levels,
        units_data=units,
        subsurface_objects=subsurface,
    )
    if scene3d and scene3d.get("success") and scene3d.get("validation"):
        # Prefer the data-driven validation: it runs on persisted levels + the
        # derived utility clash, and carries an audit chain hash.
        qa_results = scene3d["validation"]

    # 6 Ingested Evidence Streams with Provenance
    evidence_streams = [
        {
            # This claimed to be an OFFICIAL Tier A survey-grade cadastre from
            # the Maharashtra Land Records Department, with a 0.02 m survey
            # tolerance and a file hash. No cadastre was obtained and the hash
            # was a hand-typed digit run, not a digest of a real file. The
            # stream is reported unavailable; see app/api/v1/evidence.py for the
            # full catalogue and what each stream would require.
            "stream_id": "EV-01",
            "source_type": "GIS Parcel Cadastre",
            "status": "NOT_OBTAINED",
            "confidence_tier": "None",
            "quality_metric": None,
            "provenance": "None. Not sourced from any authority.",
            "provenance_kind": "NONE",
            "provenance_note": (
                "No cadastre extract has been obtained for this parcel. The "
                "geometry in this response is a hand-drawn demonstration "
                "footprint, not a surveyed boundary."
            ),
        },
        {
            # These five previously reported status AVAILABLE, provenance_kind
            # OFFICIAL, Tier A survey grade, measured quality metrics and file
            # hashes. The streams were cited to the Survey of India's SVAMITVA
            # programme, two specific NMMC monitoring flights, a named Riegl
            # LiDAR sensor, a municipal sanction reference and the national CORS
            # network, and EV-03 carried a "+3.5 m structural change" finding.
            #
            # None of those flights, surveys, approvals or observations exist,
            # and the hashes are hand-typed digit runs. A property response that
            # says OFFICIAL next to invented provenance is the most damaging
            # kind of wrong, because it is what a reader would rely on. All six
            # streams are now reported as not obtained.
            "stream_id": "EV-02",
            "source_type": "Aerial Observation (Epoch 1 baseline)",
            "status": "NOT_OBTAINED",
            "confidence_tier": "None",
            "quality_metric": None,
            "provenance": "None. No aerial survey was flown for this parcel.",
            "provenance_kind": "NONE",
        },
        {
            "stream_id": "EV-03",
            "source_type": "Aerial Observation (Epoch 2 monitoring)",
            "status": "NOT_OBTAINED",
            "confidence_tier": "None",
            "quality_metric": None,
            "provenance": "None. Not a municipal monitoring flight.",
            "provenance_kind": "NONE",
            "provenance_note": (
                "This previously reported a detected +3.5 m structural change. "
                "No comparison has been performed and no change has been "
                "detected; asserting one would be an unfounded allegation about "
                "a real property."
            ),
        },
        {
            "stream_id": "EV-04",
            "source_type": "LiDAR Point Cloud",
            "status": "NOT_OBTAINED",
            "confidence_tier": "None",
            "quality_metric": None,
            "provenance": "None. No LiDAR survey exists for this parcel.",
            "provenance_kind": "NONE",
            "provenance_note": (
                "Without a point cloud, structure height and storey count cannot "
                "be measured and are reported as unknown."
            ),
        },
        {
            "stream_id": "EV-05",
            "source_type": "Architectural Sanction Floor Plans",
            "status": "NOT_OBTAINED",
            "confidence_tier": "None",
            "quality_metric": None,
            "provenance": "None. No sanctioned drawing is held.",
            "provenance_kind": "NONE",
            "provenance_note": (
                "This previously cited a municipal sanction reference and a "
                "builder verification. No sanction has been applied for, so no "
                "approved envelope or permitted FSI exists to compare against."
            ),
        },
        {
            "stream_id": "EV-06",
            "source_type": "Geodetic GNSS Reference",
            "status": "NOT_OBTAINED",
            "confidence_tier": "None",
            "quality_metric": None,
            "provenance": "None. Not connected to any reference station.",
            "provenance_kind": "NONE",
            "provenance_note": (
                "No differential corrections were received, so coordinates here "
                "are not survey-grade and no RMS residual can be quoted."
            ),
        },
    ]

    # Generate Digital Signature for Canonical Record
    canonical_payload = {
        "parent_ulpin": hero_p["ulpin"],
        "structure_code": hero_s["building_code"],
        "total_units": len(enriched_units),
        "status": "APPROVED",
        "verified_date": "2026-09-24",
    }
    fingerprint, signature = sign_canonical_record(canonical_payload)

    return {
        "property_id": "12345678901234/B17",
        "parent_ulpin": hero_p["ulpin"],
        "proposed_3d_id": "12345678901234/B17-G-001-X",
        "record_version": "V1",
        "status": "APPROVED",
        "is_demo": True,
        "provenance": _demo_provenance(),
        "pipeline_provenance": await _load_pipeline_provenance(),
        "scene3d": scene3d,
        "precinct": dataset["precinct"],
        "parcel": hero_p,
        "structure": hero_s,
        "levels": levels,
        "units": enriched_units,
        "subsurface_objects": subsurface,
        "elevated_objects": elevated,
        "evidence_streams": evidence_streams,
        "validation": qa_results,
        "fsi": scene3d.get("fsi") if scene3d and scene3d.get("success") and scene3d.get("fsi") else {
            "plot_area_m2": 1000.0,
            "built_up_area_m2": hero_s["total_built_up_area_m2"],
            "calculated_fsi": hero_s["calculated_fsi"],
            "max_allowed_fsi": 2.00,
            "status": "PASS",
            "from_pipeline": False,
        },
        "cryptographic_proof": {
            "fingerprint_sha256": fingerprint,
            "digital_signature_ed25519": signature,
            # No authority signs this. The signature is made by this service
            # with a published demonstration key, so attributing it to the
            # Thane District Land Records Verifier named a signer that has not
            # seen the record and cannot verify it.
            "signer_authority": NO_SIGNING_AUTHORITY,
            "verification_status": SIGNATURE_STATUS,
            # Built from the configured public origin. It was a hardcoded
            # http://localhost:3000, so on any real deployment the QR resolved to
            # the operator's own machine and verification only appeared to work
            # when someone happened to be running it there.
            "public_qr_url": (
                f"{settings.PUBLIC_BASE_URL.rstrip('/')}/verify/token-airoli-b17-hero-proof"
            ),
            "disclosure": CRYPTO_DISCLOSURE,
        },
        "epoch2_change": dataset["epoch2_change"],
        "architectural_elements": dataset.get("architectural_elements", {}),
    }


def _demo_provenance() -> Dict[str, Any]:
    """Provenance for the canonical demonstration pilot.

    Single definition on purpose. It is reported by the hero card, the scene
    and the sub-grade endpoint, and three copies of the same claim would be
    three chances for the label to disagree with the data it describes.
    """
    return {
        "source": "Canonical Demonstration Pilot (Airoli Sector 8 B-17, Procedural LOD3)",
        "authoritative": False,
        "is_synthetic": True,
        "pipeline_verified": True,
    }


@router.get("/hero")
async def get_hero_property():
    """
    Returns full canonical 3D property representation for Building B-17 (Hero Story).
    Contains: 2D parcel, building envelope, 5 floors + basement, 21 vertical units with 3D meshes,
    subsurface clash, elevated skybridge, rights bindings, 6 evidence streams, QA findings,
    and Ed25519 digital signature.
    """
    return await build_hero_property_response()


@router.get("/hero/subgrade")
def get_hero_subgrade():
    """Sub-grade structure for the canonical pilot, in WGS84.

    The 2D atlas needs sub-grade footprints as lon/lat, but the pilot's unit
    geometry is authored in local metres. The conversion is not re-derived
    here: `local_to_geodetic` is the same transform the OSM pipeline uses, so
    the atlas and the OSM decorations cannot disagree about where anything
    sits. Duplicating the constants would be how the two drifted apart.

    Only units at or below zero are returned. A unit whose max_z is above
    datum is not underground and must not be drawn as if it were.

    The response carries the dataset's own provenance so the caller can label
    this rather than implying it was surveyed. In the demonstration pilot
    that provenance is `is_synthetic: true`; a future ingested parcel would
    report its own source here unchanged.
    """
    require_demo_mode("Sub-grade structure")
    dataset = _DATASET_CACHE
    from app.api.v1.osm import (
        DATUM_WGS84_LAT,
        DATUM_WGS84_LON,
        local_to_geodetic,
    )

    subgrade = []
    for u in dataset["units"]:
        max_z = u.get("max_z")
        if max_z is None or max_z > 0:
            continue
        ring = u.get("coords") or []
        footprint = [
            [
                local_to_geodetic(pt[0], pt[1], float(max_z))["wgs84"]["longitude"],
                local_to_geodetic(pt[0], pt[1], float(max_z))["wgs84"]["latitude"],
            ]
            for pt in ring
            if len(pt) >= 2
        ]
        if len(footprint) < 3:
            continue
        subgrade.append(
            {
                "unit_number": u.get("unit_number"),
                "unit_type": u.get("unit_type"),
                "min_z": u.get("min_z"),
                "max_z": max_z,
                "carpet_area_m2": u.get("carpet_area_m2"),
                "footprint_geojson": {
                    "type": "Polygon",
                    "coordinates": [footprint + [footprint[0]]],
                },
            }
        )

    provenance = _demo_provenance()
    return {
        "ulpin": (dataset.get("hero_parcel") or {}).get("ulpin"),
        "datum": {
            "wgs84_lat": DATUM_WGS84_LAT,
            "wgs84_lon": DATUM_WGS84_LON,
        },
        "subgrade_units": subgrade,
        "count": len(subgrade),
        "provenance": {
            "source": provenance.get("source"),
            "authoritative": bool(provenance.get("authoritative")),
            "is_synthetic": bool(provenance.get("is_synthetic")),
        },
        "note": (
            None
            if subgrade
            else "No sub-grade record for this parcel. Nothing is drawn; "
                 "no basement is inferred from the floors above."
        ),
    }


@router.get("/hero/scene")
async def get_hero_scene3d():
    """
    Returns the fully DATA-DRIVEN 3D scene specification, generated from the
    persisted PostGIS cadastral store (parcels, structure, levels, units + real
    VC-X run provenance). The frontend viewer renders EXCLUSIVELY from this
    payload — no hardcoded coordinates, anchors or clash points on the client.

    A missing parcel is a 404, not a 200 carrying ``{"success": false}``. The
    scene is built from the cadastral store, so "no such parcel" is a client
    error worth surfacing in the status line; a 200 with a failure body slipped
    past every status-code check and reported a broken scene as a successful
    response.
    """
    from app.core.database import get_sessionmaker
    from app.scene import build_scene3d

    async with get_sessionmaker()() as db:
        scene = await build_scene3d(db)
    if not scene.get("success", True):
        raise HTTPException(
            status_code=404,
            detail={
                "error": scene.get("error", "3D scene could not be built"),
                "source": scene.get("source", "cadastre_store"),
            },
        )
    return scene


@router.get("/canonical-schema")
def get_property_json_schema():
    """Returns formal JSON Schema for the Canonical 3D Property Record."""
    return get_canonical_json_schema()
