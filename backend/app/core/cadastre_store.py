"""
PostGIS persistence layer for cadastral parcels, vertical structures and
pipeline provenance.

Turns the VC-X outputs and the Airoli demo into *real database rows* with
real PostGIS 3D solids (PolyhedralSurfaceZ in projected UTM zone 43N) and
hash-bound asset/run records on the tamper-evident chain.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import geometry
from app.models.cadastre import Parcel, Structure, Level, Unit
from app.models.pipeline import DatasetAsset, PipelineRun

# Documented Airoli local-frame origin (UTM zone 43N, metres).
AIROLI_ORIGIN = {"easting": 298000.0, "northing": 2113500.0}
CRS_SRID = 32643


def as_wkt_ring(ring_m: List[tuple], z: Optional[float] = None) -> str:
    """Local-frame metre ring -> WKT ring in projected UTM zone 43N (with optional Z)."""
    parts = []
    for x, y in ring_m:
        e = AIROLI_ORIGIN["easting"] + float(x)
        n = AIROLI_ORIGIN["northing"] + float(y)
        parts.append(f"{e:.3f} {n:.3f}" + (f" {z:.3f}" if z is not None else ""))
    if parts and parts[0] != parts[-1]:
        parts.append(parts[0])
    return "(" + ", ".join(parts) + ")"


def polyhedral_surface_wkt(ring_m: List[tuple], z_min: float, z_max: float) -> str:
    """Builds a watertight, outward-oriented POLYHEDRALSURFACE Z prism over [z_min, z_max]."""
    ring2 = ring_m
    if len(ring2) < 3:
        raise ValueError("A prism requires at least 3 vertices.")
    r = list(ring2)
    if r[0] == r[-1]:
        r = r[:-1]
    rev = [tuple(p) for p in reversed(r)]

    def pt(x: float, y: float, z: float) -> str:
        return f"{AIROLI_ORIGIN['easting'] + x:.3f} {AIROLI_ORIGIN['northing'] + y:.3f} {z:.3f}"

    def face(ring_pts: List[tuple], z: float) -> str:
        body = ", ".join(pt(x, y, z) for x, y in ring_pts)
        body += ", " + pt(ring_pts[0][0], ring_pts[0][1], z)
        return "((" + body + "))"

    faces: List[str] = []
    faces.append(face(rev, z_min))   # bottom, outward down
    faces.append(face(r, z_max))     # top, outward up
    for i in range(len(r)):          # side quads, outward
        p0 = r[i]
        p1 = r[(i + 1) % len(r)]
        pts = [pt(p0[0], p0[1], z_min), pt(p1[0], p1[1], z_min),
               pt(p1[0], p1[1], z_max), pt(p0[0], p0[1], z_max),
               pt(p0[0], p0[1], z_min)]
        faces.append("((" + ", ".join(pts) + "))")
    return f"SRID={CRS_SRID};POLYHEDRALSURFACE Z (" + ", ".join(faces) + ")"


def polygon_wkt(ring: List[tuple], *, frame: Optional[str] = None) -> str:
    """EWKT 2D polygon (SRID-prefixed) in projected UTM (for Parcel.geom / GIS ops).

    Delegates to :mod:`app.core.geometry`, which is the single place that knows
    whether a ring is WGS84 degrees or local-frame metres.

    This used to be "local metres plus the Airoli origin" and nothing else, and
    that assumption was the bug: the OpenStreetMap / GlobalML ingest path in
    ``api.v1.parcels`` passes the source's ``ring_geo``, which is
    ``[[lon, lat], ...]`` in degrees. Adding those to the UTM origin stored
    ``298000 + lon`` / ``2113500 + lat`` -- easting 298073 where the true
    easting is 289219, tens of kilometres away, collapsed to zero area.
    Callers that already know their frame should pass ``frame=``.
    """
    return geometry.polygon_ewkt(
        ring,
        frame=frame,
        origin=(AIROLI_ORIGIN["easting"], AIROLI_ORIGIN["northing"]),
    )


def shoelace_area_m2(ring_m: List[tuple]) -> float:
    """Shoelace area of a local-frame ring (metres²)."""
    r = list(ring_m)
    if r[0] != r[-1]:
        r.append(r[0])
    s = 0.0
    for (x1, y1), (x2, y2) in zip(r, r[1:]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


_schema_lock = asyncio.Lock()
_schema_ready = False


def _ensure_schema_ddl() -> None:
    """The actual DDL. Blocking, so it must never run on the event loop.

    `CREATE EXTENSION IF NOT EXISTS postgis` takes an exclusive lock on the
    database. Every `ALTER TABLE` then queues behind whatever else is holding
    that lock. Running this inline meant a handful of concurrent requests could
    wedge the entire server: the loop was pinned inside the lock wait, so even
    `async def` handlers such as /health stopped being scheduled.
    """
    from app.core.database import Base, sync_engine

    with sync_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        Base.metadata.create_all(conn)
        # Idempotent column upgrades for tables that pre-date the spatial model.
        _ALTERS = [
            'ALTER TABLE parcels ADD COLUMN IF NOT EXISTS geom geometry(POLYGON,32643)',
            'ALTER TABLE parcels ADD COLUMN IF NOT EXISTS geom_hash varchar(64)',
            'ALTER TABLE jurisdictions ADD COLUMN IF NOT EXISTS provenance_authoritative boolean DEFAULT false',
            'ALTER TABLE jurisdictions ADD COLUMN IF NOT EXISTS rule_source varchar(200)',
            'ALTER TABLE jurisdictions ALTER COLUMN max_fsi DROP NOT NULL',
            'ALTER TABLE parcels ADD COLUMN IF NOT EXISTS data_provenance varchar(50)',
            'ALTER TABLE parcels ADD COLUMN IF NOT EXISTS provenance_authoritative boolean DEFAULT false',
            'ALTER TABLE parcels ADD COLUMN IF NOT EXISTS provenance_detail jsonb',
            'ALTER TABLE structures ADD COLUMN IF NOT EXISTS data_provenance varchar(50)',
            'ALTER TABLE structures ADD COLUMN IF NOT EXISTS provenance_authoritative boolean DEFAULT false',
            'ALTER TABLE structures ADD COLUMN IF NOT EXISTS height_basis varchar(50)',
            # FSI is only computable against a real permitted-FAR rule.
            'ALTER TABLE structures ALTER COLUMN calculated_fsi DROP NOT NULL',
            'ALTER TABLE structures ADD COLUMN IF NOT EXISTS geom_3d geometry(POLYHEDRALSURFACEZ,32643)',
            'ALTER TABLE structures ADD COLUMN IF NOT EXISTS observed_height_m float',
            'ALTER TABLE structures ADD COLUMN IF NOT EXISTS extraction_source varchar(200)',
            'ALTER TABLE levels ADD COLUMN IF NOT EXISTS geom_3d geometry(POLYHEDRALSURFACEZ,32643)',
            'ALTER TABLE units ADD COLUMN IF NOT EXISTS geom_3d geometry(POLYHEDRALSURFACEZ,32643)',
            # Builder-submitted address and per-floor names/uses. Address/locality
            # are claims carried from the submission form; level name/use are
            # what the submitter called each floor (phase C/D, rendered in the
            # detail view and the 3D scene).
            'ALTER TABLE parcels ADD COLUMN IF NOT EXISTS address varchar(300)',
            'ALTER TABLE parcels ADD COLUMN IF NOT EXISTS locality varchar(200)',
            'ALTER TABLE levels ADD COLUMN IF NOT EXISTS name varchar(200)',
            'ALTER TABLE levels ADD COLUMN IF NOT EXISTS use varchar(100)',
            'ALTER TABLE verification_cases ADD COLUMN IF NOT EXISTS basis varchar(500)',
        ]
        for stmt in _ALTERS:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass


async def ensure_schema(db: AsyncSession) -> None:
    """Creates PostGIS extension + schema (idempotent).

    The DDL runs at most once per process, and off the event loop. It used to
    run on every request and inline on the loop, which is what wedged the
    server under concurrent load; callers are read paths that only need the
    schema to already exist, so a flag is sufficient and keeps those paths off
    the DDL lock entirely.
    """
    global _schema_ready
    if _schema_ready:
        return
    async with _schema_lock:
        if _schema_ready:
            return
        await asyncio.to_thread(_ensure_schema_ddl)
        # Only latch on success, so a transient DB failure is retried by the
        # next caller rather than leaving a half-migrated schema latched good.
        _schema_ready = True
    if db is not None:
        await db.commit()


# --------------------------------------------------------------------------- #
# Dataset / run persistence
# --------------------------------------------------------------------------- #
async def upsert_parcel(
    db: AsyncSession,
    ulpin: str,
    survey_number: str,
    jurisdiction_id: str,
    polygon_wkt_2d: Optional[str],
    polygon_geojson: Dict[str, Any],
    document_area_m2: float,
    calculated_area_m2: float,
    status: str = "ACTIVE",
) -> Parcel:
    """Upserts a parcel, deriving ``geom`` from the polygon's own WGS84 coordinates.

    ``polygon_wkt_2d`` used to be assigned straight to ``parcel.geom``. Every
    caller built it with :func:`polygon_wkt`, which anchors a ring to the Airoli
    UTM origin -- so an OSM/GlobalML ring in degrees was stored ~8.8 km east of
    where it describes, the ring collapsed to a point, ``ST_Area`` returned 0 and
    ``gis_area_m2`` recorded a measured zero for 37 parcels. It is still
    accepted, because both callers pass it, but it is no longer trusted:
    ``geom`` is reprojected here from ``polygon_geojson``.

    A ring that is not in degrees leaves ``geom`` NULL and ``gis_area_m2``
    untouched. That is the only caller (the generated hero parcel
    ``12345678901234`` in ``api.v1.pipelines_api``), and it hands over bare local
    metres in a column named ``polygon_geojson``. Refusing to guess is right
    there: a 32643 polygon of guessed numbers is worse than no polygon, and the
    row keeps ``document_area_m2`` / ``calculated_area_m2`` so the area is still
    reported. It is that caller's ``polygon_geojson`` -- not this function --
    that needs fixing to carry degrees.
    """
    parcel = (await db.execute(select(Parcel).where(Parcel.ulpin == ulpin))).scalar_one_or_none()
    if parcel is None:
        parcel = Parcel(
            ulpin=ulpin,
            survey_number=survey_number,
            jurisdiction_id=jurisdiction_id,
            polygon_geojson=polygon_geojson,
            document_area_m2=document_area_m2,
            calculated_area_m2=calculated_area_m2,
            status=status,
        )
        db.add(parcel)
    # The single source of truth is the polygon's own WGS84 coordinates. The
    # supplied WKT is deliberately not read: it is the value that was wrong.
    parcel.geom = geometry.geodetic_polygon_ewkt(
        geometry.geojson_exterior_ring(polygon_geojson)
    )
    parcel.boundary_coordinates = polygon_geojson.get("coordinates")
    await db.commit()
    if parcel.geom is not None:
        # Materialise GIS-verified area from PostGIS (resolves any ring distortion).
        # Only when there is geometry to measure: ST_Area(NULL) is NULL, and
        # rounding that to 0.0 would report a measured zero area for a parcel
        # whose geometry was simply never projected.
        area = await db.execute(select(func.ST_Area(parcel.geom)))
        parcel.gis_area_m2 = round(float(area.scalar() or 0.0), 2)
        await db.commit()
    await db.refresh(parcel)
    return parcel


async def register_asset(
    db: AsyncSession,
    dataset_id: str,
    dataset_name: str,
    storage_path: str,
    fmt: str,
    size_bytes: int,
    file_sha256: str,
    provenance: Optional[Dict[str, Any]] = None,
) -> DatasetAsset:
    existing = (
        await db.execute(
            select(DatasetAsset).where(DatasetAsset.file_sha256 == file_sha256)
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    asset = DatasetAsset(
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        storage_path=storage_path,
        format=fmt,
        bytes=size_bytes,
        file_sha256=file_sha256,
        crs_epsg=CRS_SRID,
        provenance=provenance,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


async def persist_run(
    db: AsyncSession,
    result: Dict[str, Any],
    asset: Optional[DatasetAsset] = None,
    actor_id: str = "system-pipeline",
) -> PipelineRun:
    run = PipelineRun(
        pipeline_id="vertical-cadastre-extraction",
        run_hash=result["provenance"]["run_hash"],
        asset_id=asset.id if asset else None,
        actor_id=actor_id,
        status="SUCCESS",
        metrics=result.get("metrics"),
        engine=result.get("engine"),
        stages=result.get("stages"),
        provenance=result.get("provenance"),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


# --------------------------------------------------------------------------- #
# Vertical cadastre persistence (Structure + Levels + Units + 3D solids)
# --------------------------------------------------------------------------- #
async def persist_vertical_structure(
    db: AsyncSession,
    parcel: Parcel,
    vcx: Dict[str, Any],
    building_code: str,
    name: str,
    footprint_ring: List[tuple],
    ground_z: float,
) -> Structure:
    """Creates (or updates) the vertical structure with PostGIS 3D solids per level."""
    structure = (
        (
            await db.execute(
                select(Structure).where(
                    Structure.parcel_id == parcel.id,
                    Structure.building_code == building_code,
                )
            )
        )
        .scalar_one_or_none()
    )

    volumes = vcx["stages"]["volumes"]
    run_hash = vcx["provenance"]["run_hash"]
    observed_height = vcx["stages"]["building_extraction"]["extracted_height_m"]
    area = vcx["stages"]["building_extraction"]["footprint_area_m2"]

    if structure is None:
        structure = Structure(
            parcel_id=parcel.id,
            building_code=building_code,
            name=name,
            structure_type="RESIDENTIAL_COMMERCIAL",
            footprint_geojson=vcx["stages"]["building_extraction"]["footprint_geojson"],
            ground_elevation_z=ground_z,
            height_m=max(observed_height, 0.1),
            floors_count=max(1, vcx["stages"]["floor_segmentation"]["detected_floor_count"]),
            basements_count=1 if any(v["level_type"] == "BASEMENT" for v in volumes) else 0,
            total_built_up_area_m2=round(area * max(1, vcx["stages"]["floor_segmentation"]["detected_floor_count"]), 2),
            calculated_fsi=vcx["stages"]["fsi"],
            is_verified=True,
            observed_height_m=round(observed_height, 2),
            extraction_source=run_hash,
            geom_3d=polyhedral_surface_wkt(footprint_ring, ground_z - 3.5, ground_z + max(observed_height, 3.6)),
        )
        db.add(structure)
        await db.flush()

    # Levels + units per detected floor
    floor_ring = footprint_ring
    for vol in volumes:
        level = (
            (
                await db.execute(
                    select(Level).where(
                        Level.structure_id == structure.id,
                        Level.level_code == vol["level_code"],
                    )
                )
            )
            .scalar_one_or_none()
        )
        if level is None:
            level = Level(
                structure_id=structure.id,
                level_code=vol["level_code"],
                floor_number=vol["floor_number"],
                min_z=vol["min_z"],
                max_z=vol["max_z"],
                height_m=vol["height_m"],
                level_type=vol["level_type"],
                boundary_geojson=None,
                geom_3d=polyhedral_surface_wkt(floor_ring, vol["min_z"], vol["max_z"]),
            )
            db.add(level)
            await db.flush()

        # Vertical-envelope unit (whole-floor volume) with a PostGIS 3D solid.
        unit = (
            (
                await db.execute(
                    select(Unit).where(
                        Unit.level_id == level.id,
                        Unit.unit_number == vol["level_code"],
                    )
                )
            )
            .scalar_one_or_none()
        )
        if unit is None:
            area_m2 = float(vol.get("area_m2") or 0.0) or shoelace_area_m2(floor_ring)
            volume_m3 = area_m2 * float(vol.get("height_m") or 0.0)
            unit = Unit(
                structure_id=structure.id,
                level_id=level.id,
                unit_number=vol["level_code"],
                proposed_3d_id=f"B17{vol['level_code']}V1",
                unit_type="V",
                min_z=vol["min_z"],
                max_z=vol["max_z"],
                carpet_area_m2=round(area_m2, 2),
                built_up_area_m2=round(area_m2, 2),
                volume_m3=round(volume_m3, 2),
                footprint_geojson={"type": "Polygon", "coordinates": [[[float(x), float(y)] for x, y in floor_ring]]},
                mesh_geometry_3d={"extrusion": {"min_z": vol["min_z"], "max_z": vol["max_z"]}},
                geom_3d=polyhedral_surface_wkt(floor_ring, vol["min_z"], vol["max_z"]),
                status="GENERATED",
            )
            db.add(unit)
            await db.flush()
    await db.commit()
    await db.refresh(structure)
    return structure


async def upsert_pipeline_evidence(
    db: AsyncSession,
    run: PipelineRun,
    entity_type: str,
    entity_id: str,
    actor_id: str,
) -> Dict[str, Any]:
    """Writes the run onto the tamper-evident audit chain (core.hash_chain)."""
    from app.core.hash_chain import compute_audit_hash, GENESIS_HASH
    from app.core.crypto import canonicalize_json

    payload = {
        "run_hash": run.run_hash,
        "metrics": run.metrics,
        "engine": run.engine,
    }
    now_iso = datetime.now(timezone.utc).isoformat()
    audit_hash = compute_audit_hash(
        previous_hash=GENESIS_HASH,
        event_type="PIPELINE_RUN_PERSISTED",
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        timestamp_iso=now_iso,
        payload=payload,
    )
    return {
        "audit_hash": audit_hash,
        "previous_hash": GENESIS_HASH,
        "timestamp_utc": now_iso,
        "canonical_payload": canonicalize_json(payload),
        "stored": True,
    }