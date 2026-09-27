from typing import Any, Dict, List, Optional, Tuple
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.cadastre_store import AIROLI_ORIGIN, ensure_schema
from app.core.config import settings
from app.models.cadastre import Parcel, Structure, Level, Unit
from app.models.pipeline import PipelineRun, DatasetAsset
from app.pipelines.vertical_delineation import VerticalDelineationPipeline
from app.qa_engine.underground_clash import UndergroundClashDetector
from app.pipelines.synthetic_generator import generate_synthetic_airoli_dataset

HERO_ULPIN = "12345678901234"
HERO_BUILDING = "B-17"
_DELINEATOR = VerticalDelineationPipeline()
_CLASH_DETECTOR = UndergroundClashDetector()


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #
def ring_of(geojson: Dict[str, Any]) -> List[List[float]]:
    """Extracts the outer ring (list of [x, y]) from a Polygon GeoJSON."""
    return [[float(c[0]), float(c[1])] for c in geojson["coordinates"][0]]


def bbox_of(ring: List[List[float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def center_of(ring: List[List[float]]) -> List[float]:
    minx, miny, maxx, maxy = bbox_of(ring)
    return [round((minx + maxx) / 2.0, 3), round((miny + maxy) / 2.0, 3)]


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Session scope (dedicated, disposable engine)
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def _own_session():
    """Creates a fresh connection owned by the calling event loop and fully
    disposed afterwards. This deliberately avoids SQLAlchemy's shared async pool
    (whose connections are bound to uvicorn's main loop) so that the sync
    `asyncio.run()` path in FastAPI endpoints cannot hit cross-loop errors."""
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, future=True)
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = maker()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


async def build_scene3d(
    db: Optional[AsyncSession] = None,
    ulpin: str = HERO_ULPIN,
    building_code: str = HERO_BUILDING,
) -> Dict[str, Any]:
    """Generates the complete, database-derived 3D scene specification."""
    if db is None:
        async with _own_session() as session:
            return await build_scene3d(session, ulpin, building_code)
    await ensure_schema(db)

    # `jurisdiction` is dereferenced below for the FSI authority test, and a
    # lazy load there raises MissingGreenlet, because attribute access on a
    # relationship is IO and this code is not in an implicit greenlet context.
    # Eager-load it with the parcel. This was masked until now: the hero parcel
    # was never persisted, so this line was never reached.
    parcel = (await db.execute(
        select(Parcel).options(selectinload(Parcel.jurisdiction)).where(Parcel.ulpin == ulpin)
    )).scalar_one_or_none()
    if parcel is None:
        return {"success": False, "error": f"Parcel '{ulpin}' not persisted"}

    neighbors = (await db.execute(
        select(Parcel).where(Parcel.ulpin != ulpin).limit(11)
    )).scalars().all()

    structure = (await db.execute(
        select(Structure).where(
            Structure.parcel_id == parcel.id,
            Structure.building_code == building_code,
        )
    )).scalar_one_or_none()

    run = (await db.execute(
        select(PipelineRun).order_by(desc(PipelineRun.created_at)).limit(1)
    )).scalar_one_or_none()
    asset = None
    if run and run.asset_id:
        asset = (await db.execute(
            select(DatasetAsset).where(DatasetAsset.id == run.asset_id)
        )).scalar_one_or_none()

    parcel_ring = ring_of(parcel.polygon_geojson)
    center = center_of(parcel_ring)

    levels: List[Dict[str, Any]] = []
    if structure is not None:
        levels = (await db.execute(
            select(Level).where(Level.structure_id == structure.id).order_by(Level.min_z)
        )).scalars().all()
    levels_out = [
        {
            "level_code": lv.level_code,
            "floor_number": lv.floor_number,
            "level_type": lv.level_type,
            "min_z": round(lv.min_z, 2),
            "max_z": round(lv.max_z, 2),
            "height_m": round(lv.height_m, 2),
            "solid": lv.geom_3d is not None,
        }
        for lv in levels
    ]

    # ---- Extracted structure shell (PostGIS-derived) ---------------------- #
    footprint_ring = (
        ring_of(structure.footprint_geojson) if structure is not None else parcel_ring
    )
    design = generate_synthetic_airoli_dataset()
    design_structure = design["hero_structure"]
    ground_z = structure.ground_elevation_z if structure is not None else design_structure.get("ground_elevation_z", 0.0)
    roof_z = max((lv["max_z"] for lv in levels_out), default=design_structure.get("height_m", 18.0))
    basement = next((lv for lv in levels_out if str(lv["level_type"]).upper() == "BASEMENT"), None)
    if basement is None:
        basement = next((lv for lv in levels_out if str(lv["level_code"]).upper().startswith("B")), None)

    structure_payload = {
        "building_code": building_code,
        "name": structure.name if structure is not None else design_structure["name"],
        "footprint_ring": footprint_ring,
        "design_height_m": design_structure.get("height_m", 18.0),
        "observed_height_m": structure.observed_height_m if structure is not None else None,
        "extraction_source": structure.extraction_source if structure is not None else None,
        "floors_count": structure.floors_count if structure is not None else design_structure.get("floors_count", 5),
        "basements_count": structure.basements_count if structure is not None else design_structure.get("basements_count", 1),
        "ground_z": ground_z,
        "roof_z": round(roof_z, 2),
        "has_postgis_3d_solid": structure.geom_3d is not None if structure is not None else False,
        "total_built_up_area_m2": structure.total_built_up_area_m2 if structure is not None else design_structure.get("total_built_up_area_m2", 1800.0),
    }

    # ---- Units: extracted envelopes (DB) + design flats (schedule) -------- #
    # The schedule is a fallback, not a second opinion. Once units are actually
    # persisted for this structure, they are the record and the generated design
    # units describe the same 21 flats. Emitting both made /hero/scene return 42
    # units with every unit_number duplicated, one set carrying a correct
    # level_code and one not, so the viewer would have drawn each flat twice.
    units_out: List[Dict[str, Any]] = [u for u in (await _extracted_units(db, structure))]
    design_units = [] if units_out else list(design["units"])

    for u in design_units:
        mesh_info = _DELINEATOR.extrude_unit_volume(
            polygon_coords=u["coords"], min_z=u["min_z"], max_z=u["max_z"]
        )
        units_out.append({
            "source": "design",
            "unit_number": u["unit_number"],
            "proposed_3d_id": u["proposed_3d_id"],
            "level_code": u["level_code"],
            "unit_type": u["unit_type"],
            "min_z": u["min_z"],
            "max_z": u["max_z"],
            "carpet_area_m2": u["carpet_area_m2"],
            "built_up_area_m2": u["built_up_area_m2"],
            "volume_m3": u["volume_m3"],
            "ring": [[float(x), float(y)] for x, y in u["coords"]],
            "mesh_3d": mesh_info["mesh_3d"],
            "center": mesh_info["center"],
            "rights": _rights_for(u["unit_number"], u["unit_type"], building_code),
        })
    units_out.sort(key=lambda x: (x["source"] != "extracted", x["min_z"], x["unit_number"]))

    # ---- Subsurface utilities + clash (derived from parcel + basement) ---- #
    b_min = basement["min_z"] if basement else -3.5
    b_max = basement["max_z"] if basement else 0.0
    minx, miny, maxx, maxy = bbox_of(parcel_ring)
    pipe_z = round(b_min + 0.3, 2)
    utility = {
        "code": "PIPE-DRAIN-01",
        "type_code": "X",
        "description": "Storm-water drain main (schematic, derived from parcel bounds)",
        "min_z": pipe_z,
        "max_z": pipe_z + 0.8,
        "geometry_3d": {
            "type": "PipeLine",
            "start": [round(minx - 2, 2), round((miny + maxy) / 2, 2), pipe_z],
            "end": [round(maxx + 2, 2), round((miny + maxy) / 2, 2), pipe_z],
            "radius": 0.4,
        },
    }
    tunnel = {
        "code": "METRO-TUNNEL-S8",
        "type_code": "X",
        "description": "Section-8 metro transit tunnel (schematic, below basement datum)",
        "min_z": -10.0,
        "max_z": -7.5,
        "geometry_3d": {
            "type": "TunnelLine",
            "start": [round(maxx - 15, 2), round(miny - 5, 2), -10.0],
            "end": [round(maxx - 15, 2), round(maxy + 5, 2), -10.0],
            "radius": 2.5,
        },
    }
    clash = _CLASH_DETECTOR.check_basement_utility_clash(
        basement_polygon_coords=footprint_ring,
        basement_min_z=b_min,
        basement_max_z=b_max,
        utility_start_xyz=utility["geometry_3d"]["start"],
        utility_end_xyz=utility["geometry_3d"]["end"],
        utility_radius_m=utility["geometry_3d"]["radius"],
        utility_code=utility["code"],
    )

    # ---- Architecture: extruded / generated from footprint + levels ------ #
    architecture = _architecture(footprint_ring, ground_z, roof_z, levels_out)
    massing_envelope = _massing_envelope(footprint_ring, levels_out)

    # ---- Elevated objects (derived) --------------------------------------- #
    sky_z = round(max([lv["max_z"] for lv in levels_out] or [roof_z]) - 4.0, 2)
    elevated_out = [
        {
            "code": "SKYBRIDGE-S8-01",
            "type_code": "E",
            "min_z": sky_z,
            "max_z": round(sky_z + 3.2, 2),
            "geometry_3d": {
                "type": "Skybridge",
                "start": [round(maxx_fb(footprint_ring), 2), round(center[1], 2), sky_z],
                "end": [round(maxx_fb(footprint_ring) + 8, 2), round(center[1], 2), sky_z],
                "width": 3.0,
                "height": 3.2,
            },
        },
        {
            "code": "AIR-COLUMN-B17",
            "type_code": "A",
            "min_z": round(roof_z, 2),
            "max_z": round(roof_z + 12.0, 2),
            "geometry_3d": {
                "type": "AirColumn",
                "footprint": [list(p) for p in footprint_ring],
                "min_z": round(roof_z, 2),
                "max_z": round(roof_z + 12.0, 2),
            },
        },
    ]

    # ---- FSI: computed from recorded plot + built-up areas ---------------- #
    # The permitted ceiling comes from the jurisdiction record and is only used
    # when that record is authoritative; otherwise no verdict is issued.
    from app.qa_engine.fsi_engine import FSIEngine

    fsi_engine = FSIEngine()
    plot_area = float(parcel.gis_area_m2 or parcel.calculated_area_m2 or 0.0)
    built_up = float(structure_payload["total_built_up_area_m2"])
    jurisdiction = getattr(parcel, "jurisdiction", None)
    jurisdiction_authoritative = bool(getattr(jurisdiction, "provenance_authoritative", False))
    inputs_authoritative = bool(
        getattr(parcel, "provenance_authoritative", False)
        and getattr(structure, "provenance_authoritative", False)
    )
    fsi = fsi_engine.calculate_fsi(
        plot_area_m2=plot_area,
        total_built_up_area_m2=built_up,
        max_allowed_fsi=(float(jurisdiction.max_fsi) if jurisdiction and jurisdiction_authoritative else None),
        jurisdiction_name=(f"{jurisdiction.code} / {jurisdiction.name}" if jurisdiction else None),
        inputs_authoritative=inputs_authoritative,
    )
    fsi["from_pipeline"] = structure is not None

    # ---- QA validation against extracted verticals + derived clash -------- #
    validation = _validation(parcel, structure, levels_out, design, utility)

    # ---- Provenance -------------------------------------------------------- #
    provenance = _provenance(run, asset, structure, clash)

    return {
        "success": True,
        "meta": {
            "property_id": f"{ulpin}/{building_code}",
            "parent_ulpin": ulpin,
            "building_code": building_code,
            "crs": "EPSG:7755 (local grid) / EPSG:32643 (PostGIS)",
            "engine": "VC-X extraction + scene architect (data-driven)",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "center": center,
            "ground_z": ground_z,
            "roof_z": round(roof_z, 2),
        },
        "parcel": {
            "ulpin": parcel.ulpin,
            "survey_number": parcel.survey_number,
            "status": parcel.status,
            "ring": parcel_ring,
            "area_m2": round(float(parcel.gis_area_m2 or parcel.calculated_area_m2 or 0.0), 2),
            "postgis_verified": parcel.gis_area_m2 is not None,
        },
        "neighbors": [
            {
                "ulpin": n.ulpin,
                "status": n.status,
                "ring": ring_of(n.polygon_geojson),
                "area_m2": round(float(n.gis_area_m2 or n.calculated_area_m2 or 0.0), 2),
            }
            for n in neighbors
        ],
        "structure": structure_payload,
        "levels": levels_out,
        "units": units_out,
        "subsurface_objects": [utility, tunnel],
        "clash": clash,
        "elevated_objects": elevated_out,
        "architecture": architecture,
        "massing_envelope": massing_envelope,
        "fsi": fsi,
        "validation": validation,
        "provenance": provenance,
    }


# --------------------------------------------------------------------------- #
# Pieces
# --------------------------------------------------------------------------- #
def maxx_fb(ring: List[List[float]]) -> float:
    return bbox_of(ring)[2]


async def _extracted_units(db: AsyncSession, structure: Optional[Structure]) -> List[Dict[str, Any]]:
    if structure is None:
        return []
    rows = (await db.execute(
        select(Unit, Level)
        .join(Level, Unit.level_id == Level.id, isouter=True)
        .where(Unit.structure_id == structure.id)
        .order_by(Unit.min_z)
    )).all()
    out: List[Dict[str, Any]] = []
    for u, parent_level in rows:
        ring = ring_of(u.footprint_geojson)
        mesh = _DELINEATOR.extrude_unit_volume(polygon_coords=ring, min_z=u.min_z, max_z=u.max_z)
        out.append({
            "source": "extracted",
            "unit_number": u.unit_number,
            "proposed_3d_id": u.proposed_3d_id,
            # The owning level's code, not the unit number. These were the same
            # string before only because no hero unit was ever persisted, so the
            # mistake was invisible; seeding the hero made 21 units report
            # level_code "P01" instead of "B1".
            "level_code": parent_level.level_code if parent_level is not None else u.unit_number,
            "unit_type": u.unit_type or "V",
            "min_z": u.min_z,
            "max_z": u.max_z,
            "carpet_area_m2": u.carpet_area_m2,
            "built_up_area_m2": u.built_up_area_m2,
            "volume_m3": u.volume_m3,
            "ring": ring,
            "mesh_3d": mesh["mesh_3d"],
            "center": mesh["center"],
            "has_postgis_solid": u.geom_3d is not None,
            "rights": [{
                "right_type": "MODELLED_RIGHT",
                "party_name": "Extracted vertical envelope · B-17",
                "party_type": "SYSTEM",
                "share_pct": 100.0,
                "encumbrance_status": "MODELLED",
                "color_hex": "#6B7280",
            }],
        })
    return out


def _rights_for(unit_number: str, unit_type: str, building_code: str = HERO_BUILDING) -> List[Dict[str, Any]]:
    """Rights shown for one unit.

    The mortgage and easement below describe a single flat in the hero building.
    Keying them on the unit number alone applied them to flat 201 of every
    building in the precinct, so an 11-building scene claimed 11 separate
    State Bank of India liens. They are scoped to the hero building to match
    what /rights/summary reports.
    """
    if unit_number == "201" and building_code == HERO_BUILDING:
        return [
            {
                "right_type": "MODELLED_RIGHT",
                "party_name": "Karan Malhotra & Priya Malhotra",
                "party_type": "MODELLED",
                "share_pct": 100.0,
                "encumbrance_status": "MODELLED",
                "color_hex": "#10B981",
            },
            {
                "right_type": "MORTGAGE",
                # Not a real bank. A nationalised bank was being named as the
                # holder of an encumbrance on a building it knows nothing about.
                "party_name": "Demo lender (not a real institution)",
                "party_type": "FINANCIAL_INSTITUTION",
                "mortgage_amount_inr": 8500000.0,
                "encumbrance_status": "MODELLED",
                "color_hex": "#EF4444",
            },
            {
                "right_type": "EASEMENT",
                "party_name": "Building B-17 Cooperative Housing Society",
                "party_type": "HOUSING_SOCIETY",
                "easement_purpose": "Access to Shared Corridor & Fire Evacuation Staircase",
                "encumbrance_status": "MODELLED",
                "color_hex": "#3B82F6",
            },
        ]
    if unit_type == "P":
        return [{
            "right_type": "MODELLED_RIGHT",
            "party_name": "Building B-17 CHS Common Property",
            "party_type": "HOUSING_SOCIETY",
            "share_pct": 100.0,
            "encumbrance_status": "MODELLED",
            "color_hex": "#6B7280",
        }]
    return [{
        "right_type": "MODELLED_RIGHT",
        "party_name": "MODELLED_PARTY",
        "party_type": "MODELLED",
        "share_pct": 100.0,
        "encumbrance_status": "MODELLED",
        "color_hex": "#10B981",
    }]


def _massing_envelope(
    footprint_ring: List[List[float]],
    levels_out: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Per-level building volume, from real elevations and a declared footprint.

    What this is: the structure footprint extruded through each level's
    ``min_z``/``max_z``. Both inputs are real -- the footprint is declared
    survey data on the structure row, and the Z bands come from the level rows
    with consistent storey heights.

    What this is not: a floor plate. Nothing in the data records the plan shape
    of an individual storey. ``architecture.slabs`` already draws a plate at
    each level's ``max_z``, and because every level in the seed shares one
    footprint those six plates are geometrically identical -- which reads as
    "each floor has this exact outline" when no such survey exists. The
    envelope makes the same span explicit as a volume and labels it, so a
    renderer shows a massing box and calls it that.

    The distinction is the whole point of this block existing. Drawing the
    envelope is honest; drawing it and calling it a slab is not.
    """
    if not footprint_ring or not levels_out:
        return {
            "available": False,
            "reason": "no footprint or no levels to extrude",
            "levels": [],
        }

    minx, miny, maxx, maxy = bbox_of(footprint_ring)
    boxes = []
    for lv in levels_out:
        z0 = round(float(lv["min_z"]), 2)
        z1 = round(float(lv["max_z"]), 2)
        boxes.append({
            "level_code": lv["level_code"],
            "level_type": lv.get("level_type"),
            "min_x": round(float(minx), 2),
            "min_y": round(float(miny), 2),
            "max_x": round(float(maxx), 2),
            "max_y": round(float(maxy), 2),
            "min_z": z0,
            "max_z": z1,
            "height_m": round(z1 - z0, 2),
        })

    return {
        "available": True,
        "frame": "local_metres",
        "frame_note": (
            "Bounds are the generator's local metre frame, the same frame as "
            "structure.footprint_ring, architecture.slabs and units[].mesh_3d. "
            "They are not lon/lat and must not be plotted on a map."
        ),
        "plan_basis": "declared_structure_footprint",
        "elevation_basis": "level_min_max_z",
        "is_massing_envelope": True,
        "not_a_floor_plate": (
            "Each box is the declared footprint extruded through a measured "
            "storey band. The plan outline of an individual storey is not "
            "surveyed and is not implied by these boxes."
        ),
        "footprint_area_m2": round((maxx - minx) * (maxy - miny), 2),
        "levels": boxes,
    }


def _architecture(
    footprint_ring: List[List[float]],
    ground_z: float,
    roof_z: float,
    levels_out: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Procedurally derives architecture (slabs / columns / core / piles…) from
    the persisted footprint and level Z-bounds — no cached design dict."""
    minx, miny, maxx, maxy = bbox_of(footprint_ring)
    cx, cy = center_of(footprint_ring)
    bw = maxx - minx
    bd = maxy - miny

    slabs = []
    for lv in levels_out:
        slabs.append({
            "name": f"SLAB-{lv['level_code']}",
            "bounds": [minx, miny, maxx, maxy],
            "z": round(lv["max_z"], 2),
            "thickness": 0.35,
            "level_code": lv["level_code"],
        })

    columns = []
    step = 4.5
    x = minx + 1.2
    idx = 0
    while x < maxx - 1.0:
        y = miny + 1.2
        while y < maxy - 1.0:
            columns.append({
                "id": f"C{idx:02d}",
                "x": round(x, 2),
                "y": round(y, 2),
                "min_z": ground_z,
                "max_z": round(roof_z, 2),
                "size": [0.45, 0.45],
            })
            idx += 1
            y += step
        x += step

    core_w = bw * 0.30
    core_d = bd * 0.30
    central_core = {
        "bounds": [cx - core_w / 2, cy - core_d / 2, cx + core_w / 2, cy + core_d / 2],
        "min_z": ground_z,
        "max_z": round(roof_z, 2),
    }

    balconies = []
    habitable = [lv for lv in levels_out if str(lv["level_type"]).upper() in ("GROUND", "HABITABLE")]
    for lv in habitable[:6]:
        for facade in ("SOUTH", "NORTH"):
            balconies.append({
                "level_code": lv["level_code"],
                "facade": facade,
                "z": lv["min_z"],
                "railing_height": 1.05,
                "bounds": [
                    cx - bw / 6.0,
                    cy + (bd / 2.0 - 0.3) if facade == "NORTH" else cy - (bd / 2.0 - 0.3),
                    cx + bw / 6.0,
                    cy + (bd / 2.0 - 0.3 + 1.2) if facade == "NORTH" else cy - (bd / 2.0 - 0.3 + 1.2),
                ],
            })

    roof_crown = {
        "parapet": {"height": 0.9, "offset": 0.0},
        "lift_machine_room": {
            "center": [cx, cy],
            "size": [bw / 4.0, bd / 4.0, 2.4],
            "base_z": round(roof_z, 2),
        },
        "solar_pv_array": {
            "cols": 8,
            "rows": 3,
            "tilt_deg": 18.0,
            "base_z": round(roof_z + 1.0, 2),
            "bounds": [minx, miny, maxx, maxy],
        },
        "water_tanks": [
            {"code": "OHT-01", "position": [cx - bw * 0.18, cy + bd * 0.10], "base_z": round(roof_z + 1.5, 2), "radius": 0.9, "height": 1.6, "color": "#3B82F6"},
            {"code": "OHT-02", "position": [cx + bw * 0.18, cy + bd * 0.10], "base_z": round(roof_z + 1.5, 2), "radius": 0.9, "height": 1.6, "color": "#EF4444"},
        ],
    }

    protrude = 0.3
    piles = []
    bx = minx + 0.6
    pi = 0
    while bx < maxx - 0.4:
        by = miny + 0.6
        while by < maxy - 0.4:
            piles.append({
                "id": f"P{pi:02d}",
                "x": round(bx, 2),
                "y": round(by, 2),
                "top_z": round(ground_z - 0.5, 2),
                "bottom_z": round(ground_z - 3.3 - protrude, 2),
                "radius": 0.35,
            })
            pi += 1
            by += 3.0
        bx += 3.0

    foundation = {
        "raft_slab": {"bounds": [minx, miny, maxx, maxy], "z": round(ground_z - 0.5, 2), "thickness": 0.5},
        "piles": piles,
        "retaining_walls": {"offset": 0.4},
    }

    return {
        "slabs": slabs,
        "columns": columns,
        "central_core": central_core,
        "balconies": balconies,
        "roof_crown": roof_crown,
        "foundation": foundation,
    }


def _validation(
    parcel: Parcel,
    structure: Optional[Structure],
    levels_out: List[Dict[str, Any]],
    design: Dict[str, Any],
    utility: Dict[str, Any],
) -> Dict[str, Any]:
    from app.qa_engine import TopologyQAEngine
    from app.core.hash_chain import compute_audit_hash, GENESIS_HASH
    from app.core.crypto import canonicalize_json

    parcel_data = {
        "ulpin": parcel.ulpin,
        "polygon_geojson": parcel.polygon_geojson,
        "document_area_m2": parcel.document_area_m2,
        "calculated_area_m2": float(parcel.gis_area_m2 or parcel.calculated_area_m2 or 0.0),
    } if structure is None else None

    structure_data = (
        {
            "building_code": structure.building_code,
            "footprint_geojson": structure.footprint_geojson,
            "height_m": structure.height_m,
        }
        if structure is not None else design["hero_structure"]
    )

    levels_data = (
        [{"level_code": lv["level_code"], "min_z": lv["min_z"], "max_z": lv["max_z"], "level_type": lv["level_type"]} for lv in levels_out]
        or design["levels"]
    )

    units_data = design["units"]
    survey_sources = None

    qa = TopologyQAEngine().run_all_rules(
        parcel_data=parcel_data or design["hero_parcel"],
        structure_data=structure_data,
        levels_data=levels_data,
        units_data=units_data,
        subsurface_objects=[utility],
        survey_sources=survey_sources,
    )

    audit_hash = compute_audit_hash(
        previous_hash=GENESIS_HASH,
        event_type="QA_VALIDATION_SCENE3D",
        entity_type="PROPERTY",
        entity_id=parcel.ulpin,
        actor_id="scene-architect",
        timestamp_iso=datetime.now(timezone.utc).isoformat(),
        payload={"total_rules": qa["total_rules"], "failed_rules": qa["failed_rules"]},
    )
    return {**qa, "audit_hash": audit_hash}


def _provenance(
    run: Optional[PipelineRun],
    asset: Optional[DatasetAsset],
    structure: Optional[Structure],
    clash: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "engine": "vertical-cadastre-extraction (deterministic-first)",
        "run_hash": run.run_hash if run else None,
        "run_created_at": run.created_at.isoformat() if run and run.created_at else None,
        "status": run.status if run else "NO_RUN",
        "metrics": run.metrics if run else None,
        "actor_id": run.actor_id if run else None,
        "asset": {
            "dataset_id": asset.dataset_id if asset else None,
            "format": asset.format if asset else None,
            "file_sha256": asset.file_sha256 if asset else None,
        },
        "structure": {
            "observed_height_m": structure.observed_height_m if structure else None,
            "extraction_source": structure.extraction_source if structure else None,
        },
        "clash": {
            "rule_id": clash.get("rule_id"),
            "has_clash": clash.get("has_clash"),
            "severity": clash.get("severity"),
            "penetration_length_m": clash.get("penetration_length_m"),
        },
    }