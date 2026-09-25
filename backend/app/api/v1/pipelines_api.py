from typing import Any, Dict, Iterable, Optional, List, Sequence
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from pydantic import BaseModel, Field

from app.core.security import get_current_user_required, require_roles, TokenPayload, RoleEnum

from app.pipelines.spatial_pipelines import spatial_pipelines_registry
from app.pipelines.vertical_cadastre_pipeline import VerticalCadastrePipeline
from app.pipelines.cpp_kernels import benchmark_ground_profile
from app.pipelines.sample_data import ensure_sample, list_datasets, default_sample_dir

router = APIRouter(prefix="/pipelines", tags=["Multi-Language High-Performance Spatial Pipelines"])

STATE_PIPELINE_OP = require_roles([RoleEnum.STATE_ADMIN, RoleEnum.DISTRICT_VERIFIER])


class PipelineRunRequest(BaseModel):
    pipeline_id: str = Field(..., description="ID of the pipeline to run (e.g., 'nbc-encroachment')")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Pipeline configuration parameters")


@router.get("/catalog")
def get_pipeline_catalog():
    """
    Returns the catalog of all 8 specialized 3D spatial analysis pipelines,
    including a description and parameter schema for each.

    None of these pipelines determines compliance, reads a regulation, validates
    against a published standard or consults an authority. They compute geometry
    and arithmetic on caller-supplied inputs, and the "reference_material" field
    on each entry is background reading rather than an implementation claim.
    """
    return {
        "count": 8,
        "pipelines": spatial_pipelines_registry.get_catalog(),
        "scope_note": (
            "Analysis only. No pipeline in this catalog determines legal "
            "compliance, reads a sanctioned plan or development control regulation, "
            "validates against a published standard, or reports a finding to any "
            "authority. Results are geometry and arithmetic on the inputs the "
            "caller supplied. Any limit, setback, FAR or clearance compared "
            "against is a caller assumption, not a verified requirement."
        ),
    }


@router.post("/run")
def run_spatial_pipeline(request: PipelineRunRequest, async_run: bool = False, _auth: TokenPayload = Depends(STATE_PIPELINE_OP)):
    """
    Executes a specialized 3D spatial analysis pipeline.
    Calculates exact spatial geometries, compliance findings, and comparative polyglot benchmarks.

    Pass ``async_run=true`` to execute via the Celery worker queue and return a
    task id immediately (run status later via ``/pipelines/async/{task_id}``).
    """
    if async_run:
        from app.worker import run_spatial_pipeline as celery_task
        async_res = celery_task.delay(request.pipeline_id, request.parameters or {})
        return {
            "success": True,
            "async": True,
            "task_id": async_res.id,
            "pipeline_id": request.pipeline_id,
            "status_poll_endpoint": f"/api/v1/pipelines/async/{async_res.id}",
        }
    try:
        result = spatial_pipelines_registry.execute_pipeline(
            pipeline_id=request.pipeline_id,
            params=request.parameters
        )
        return {
            "success": True,
            "data": result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline execution error: {str(e)}")


@router.get("/async/{task_id}")
def get_async_pipeline_result(task_id: str, _auth: TokenPayload = Depends(STATE_PIPELINE_OP)):
    """Polls the result of an async pipeline run by Celery task id."""
    from celery.result import AsyncResult
    from app.worker import celery_app

    res = AsyncResult(task_id, app=celery_app)
    if res.state == "PENDING":
        return {"state": "PENDING", "task_id": task_id, "status": "queued_or_starting"}
    if res.state == "FAILURE":
        return {"state": "FAILURE", "task_id": task_id, "error": str(res.info)}
    return {"state": res.state, "task_id": task_id, "result": res.info}


_BENCHMARK_CACHE: Optional[Dict[str, Any]] = None


@router.get("/benchmarks")
def get_pipeline_benchmarks(force: bool = False):
    """
    Returns REAL measured wall-clock benchmarks comparing the pure-Python reference
    against the native C++ (ctypes, g++ -O3) kernel for the shared heavy workload
    (per-cell LiDAR ground profiling). Results are cached in-memory for sub-second responses.
    Pass `force=true` to re-measure.
    """
    global _BENCHMARK_CACHE
    if _BENCHMARK_CACHE is None or force:
        _BENCHMARK_CACHE = {
            "measured": True,
            "measured_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            **benchmark_ground_profile(n=250_000, repeat=3),
            "note": "Timings measured on this machine in-container; replaces hardcoded marketing numbers.",
        }
    return _BENCHMARK_CACHE


@router.get("/data-sets")
def get_datasets(sample_dir: Optional[str] = None):
    """Lists discovered real point-cloud datasets available for VC-X execution."""
    from app.core.demo_gate import demo_mode_enabled
    sample_dir = sample_dir or default_sample_dir()
    if demo_mode_enabled():
        try:
            ensure_sample(sample_dir)  # materialize the bundled sample on first request
        except Exception:
            pass
    datasets = list_datasets(sample_dir)
    return {
        "count": len(datasets),
        "datasets": [
            {
                "dataset_id": d["dataset_id"],
                "name": d["name"],
                "file": d["file"],
                "point_count": (d["manifest"].get("las_stats") or {}).get("point_count"),
                "classification": (d["manifest"].get("las_stats") or {}).get("classification_counts"),
                "ground_truth": (d["manifest"].get("ground_truth") or {}).get("hero_building"),
                "crs": d["manifest"].get("crs"),
                "server_path": d["path"],
            }
            for d in datasets
        ],
    }


# The hero building's footprint as VC-X extracts it: a 30 x 17 m rectangle in the
# pipeline's own local metric frame, the same frame every level and unit in the
# run is measured in.
HERO_PARCEL_RING_M = ((145.0, 144.0), (175.0, 144.0), (175.0, 161.0), (145.0, 161.0))


def _utm43n_ewkt(projected: Iterable[Sequence[float]]) -> str:
    """EWKT in EPSG:32643 for an already-projected ring, in the form PostGIS reads.

    The projection itself comes from :mod:`app.core.geometry`; only the serialising
    is done here. ``geometry.utm43n_polygon_ewkt`` writes ``POLYGON(x y, ...)``
    where WKT requires ``POLYGON((x y, ...))`` -- the ring needs its own
    parentheses -- and PostGIS refuses that string with "parse error - invalid
    geometry" at the first coordinate. ``upsert_parcel`` still takes this
    argument, and while it derives ``geom`` from the GeoJSON itself it should not
    be handed a second mislabelled value in the same write. The fix belongs in
    the shared helper; this can go back to calling it once it is there.
    """
    from shapely import to_wkt
    from shapely.geometry import Polygon

    from app.core import geometry

    ring = [(float(x), float(y)) for x, y in projected]
    return f"SRID={geometry.SRID_UTM43N};{to_wkt(Polygon(ring), rounding_precision=3, trim=True)}"


def _hero_parcel_boundary(
    ring: Optional[Iterable[Sequence[float]]] = None,
) -> Optional[Dict[str, Any]]:
    """The hero parcel boundary as WGS84 GeoJSON, with the EWKT that matches it.

    Returns ``None`` when the ring cannot be placed on the map honestly, and the
    caller writes nothing rather than a guessed polygon.

    Why this exists: ``parcels.polygon_geojson`` is served to clients as WGS84
    GeoJSON -- ``GET /parcels/geojson`` emits it straight into a FeatureCollection
    as ``geometry`` -- and it is what
    :func:`app.core.cadastre_store.upsert_parcel` reprojects into ``parcels.geom``.
    This caller handed it ``[[145, 144], [175, 144], ...]``, which are metres in
    VC-X's local frame, so every reader had a choice between believing the column
    name and believing the numbers. ``upsert_parcel`` now reads the frame, finds
    metres, and correctly leaves ``geom`` NULL -- which leaves this caller as the
    only thing still publishing the lie.

    The fix is to convert rather than to drop the boundary: an anchored ring is
    georeferenced, so the row gets a real ``geom`` and a real ST_Area instead of
    a NULL column, and the ring can finally mean what its name says. It is still
    an *assumption*, not a survey -- :data:`app.core.geometry.ANCHOR_NOTE` spells
    out that the origin is this repository's guess at its demo jurisdiction -- so
    the basis is returned in ``geometry_basis`` and stored on the row, which is
    what ``app.core.builder_records`` does for the same local-frame ring on the
    builder intake path.

    A ring that is not metres is not anchored. :func:`app.core.geometry.classify_frame`
    decides, and a ring it cannot classify is refused rather than placed twice.
    """
    from app.core import geometry
    from app.core.cadastre_store import AIROLI_ORIGIN

    points = list(ring if ring is not None else HERO_PARCEL_RING_M)
    # A ring may arrive closed -- GeoJSON exterior rings are, and this function's
    # own output is. The repeated vertex is dropped before projecting, so a ring
    # handed back in gains no vertex each time and the conversion is idempotent
    # rather than walking its output one step further out on every call.
    if len(points) > 1 and tuple(points[0]) == tuple(points[-1]):
        points = points[:-1]
    frame = geometry.classify_frame(points)
    origin = (float(AIROLI_ORIGIN["easting"]), float(AIROLI_ORIGIN["northing"]))

    try:
        if frame == geometry.FRAME_WGS84:
            # Already degrees. Reproject straight through, anchored = nothing.
            projected = geometry.geodetic_ring_to_utm43n(points)
            geodetic = [(float(x), float(y)) for x, y in points]
            anchored = False
        elif frame == geometry.FRAME_LOCAL_METRES:
            projected = geometry.anchor_local_ring(points, origin)
            geodetic = geometry.utm43n_ring_to_wgs84(projected)
            anchored = True
        else:
            return None
        ewkt = _utm43n_ewkt(projected)
    except geometry.GeometryRefused:
        return None

    closed = [[round(lon, 9), round(lat, 9)] for lon, lat in geodetic]
    closed.append(list(closed[0]))
    if anchored:
        # anchor_record() so every reader keys on the same frame markers, with
        # this write's own subject added: ANCHOR_NOTE says "the submitter drew
        # this footprint", which is true of the builder path and not of a run
        # where the ring came out of the extractor.
        geometry_basis = {
            **geometry.anchor_record(origin),
            "geometry_note": (
                "VC-X extracted this footprint in its own local metric frame. The "
                "coordinates below are that drawing anchored to the documented "
                "origin, so they name an approximate position rather than a "
                "measured one."
            ),
        }
    else:
        geometry_basis = {
            "geometry_frame": geometry.FRAME_WGS84,
            "georeferenced": True,
            "crs": geometry.CRS_WGS84,
        }
    return {
        "polygon_geojson": {"type": "Polygon", "coordinates": [closed]},
        "polygon_wkt_2d": ewkt,
        "geometry_basis": geometry_basis,
        "anchored": anchored,
        "crs": geometry.CRS_UTM43N if anchored else geometry.CRS_WGS84,
    }


async def _persist_run_result(result: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    """Registers the asset dataset + run + vertical structure in PostGIS."""
    from app.core.database import get_sessionmaker
    from app.core.cadastre_store import (
        register_asset,
        persist_run,
        persist_vertical_structure,
        upsert_parcel,
        ensure_schema,
    )
    from app.models.cadastre import Parcel
    from sqlalchemy import select

    async with get_sessionmaker()() as db:
        await ensure_schema(db)
        asset_info = result.get("asset", {})
        asset = await register_asset(
            db,
            dataset_id=f"asset-{asset_info.get('file_sha256', '')[:12]}",
            dataset_name=asset_info.get("filename", "uploaded-asset"),
            storage_path=f"/app/data/{asset_info.get('filename', '')}",
            fmt=(asset_info.get("format") or "las").lower(),
            size_bytes=0,
            file_sha256=asset_info.get("file_sha256", ""),
            provenance={"source": "VC-X", "bounds": asset_info.get("bounds")},
        )
        run = await persist_run(db, result, asset=asset, actor_id=actor_id)

        # Persist the hero vertical structure (B-17) with PostGIS 3D solids.
        hero_parcel: Dict[str, Any] = {"written": False, "reason": "structure persist did not run"}
        try:
            parcel = (await db.execute(select(Parcel).where(Parcel.ulpin == "12345678901234"))).scalar_one_or_none()
            if parcel is None:
                boundary = _hero_parcel_boundary()
                if boundary is None:
                    # Nothing georeferenced and no way to make it so honestly.
                    # No polygon is written: a row whose geometry is a guess is
                    # worse than a row with none, and the structure needs the
                    # parcel to hang off.
                    hero_parcel = {
                        "written": False,
                        "reason": (
                            "the extracted footprint is in a frame that cannot be placed on the map, "
                            "so no boundary was written"
                        ),
                    }
                else:
                    parcel = await upsert_parcel(
                        db,
                        ulpin="12345678901234",
                        survey_number="S-17/SEC-08/AIROLI",
                        jurisdiction_id="JUR-AIROLI-S8",
                        polygon_wkt_2d=boundary["polygon_wkt_2d"],
                        polygon_geojson=boundary["polygon_geojson"],
                        document_area_m2=510.0,
                        calculated_area_m2=510.0,
                        status="APPROVED",
                    )
                    # The position is the anchoring assumption, so it says so on
                    # the row. Every read of this geometry -- the map layer, the
                    # identifier derivation on acceptance -- has to be able to see
                    # that the coordinates name an approximate location.
                    parcel.provenance_detail = {
                        **(parcel.provenance_detail or {}),
                        **boundary["geometry_basis"],
                    }
                    parcel.provenance_authoritative = False
                    await db.commit()
                    hero_parcel = {
                        "written": True,
                        "ulpin": parcel.ulpin,
                        "anchored": boundary["anchored"],
                        "crs": boundary["crs"],
                        "gis_area_m2": parcel.gis_area_m2,
                        "geometry_basis": boundary["geometry_basis"],
                    }
            await persist_vertical_structure(
                db,
                parcel,
                result,
                building_code="B-17",
                name="Bhu-Drishti HQ — Airoli Sector 8 (B-17)",
                footprint_ring=[list(p) for p in HERO_PARCEL_RING_M],
                ground_z=0.0,
            )
            hero_parcel["structure_persisted"] = True
        except Exception as exc:  # noqa: BLE001 - best-effort, but not silent
            # The run and the asset are already committed, so this stays
            # best-effort -- but the response says what did not happen rather
            # than reporting a hero parcel it never wrote. A caller reading
            # `written: false` with no reason cannot tell a deliberate refusal
            # from a database that rejected the row.
            hero_parcel = {
                **hero_parcel,
                "written": False,
                "structure_persisted": False,
                "reason": "the parcel or structure write failed; the run and asset were stored",
                "error": f"{type(exc).__name__}: {exc}".strip(),
            }

        return {
            "persisted": True,
            "asset_id": asset.id,
            "run_id": run.id,
            "run_hash": run.run_hash,
            "hero_parcel": hero_parcel,
        }


@router.post("/vertical-cadastre/run")
async def run_vertical_cadastre(dataset_id: str = "airoli-s8-hero-lidar", actor_id: str = "system-pipeline", persist: bool = True, _auth: TokenPayload = Depends(STATE_PIPELINE_OP)):
    """
    Executes the REAL Vertical Cadastre Extraction pipeline (VC-X) over a discovered
    dataset: ingestion -> per-cell ground profile (native C++) -> building extraction ->
    floor segmentation -> vertical delineation -> QA/FSI -> metrics vs ground truth ->
    provenance hash chain. Optionally persists the run + PostGIS solids (default: yes).
    """
    import os

    datasets = list_datasets()
    match = [d for d in datasets if d["dataset_id"] == dataset_id]
    if match:
        from app.core.demo_gate import require_demo_mode
        require_demo_mode("Bundled Sample LiDAR Point Cloud")
        try:
            result = VerticalCadastrePipeline().run_sample()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"VC-X execution error: {str(e)}")
    else:
        upload_root = "/app/data/uploads"
        ds_dir = os.path.join(upload_root, dataset_id)
        if not os.path.isdir(ds_dir):
            raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")
        asset = next(
            (os.path.join(ds_dir, f) for f in os.listdir(ds_dir) if f.endswith((".las", ".laz", ".csv"))),
            None,
        )
        if not asset:
            raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' has no point-cloud asset")
        try:
            result = VerticalCadastrePipeline().run_real(asset_path=asset, actor_id=actor_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"VC-X execution error: {str(e)}")

    persisted = None
    if persist:
        try:
            persisted = await _persist_run_result(result, actor_id)
        except Exception as e:
            persisted = {"persisted": False, "error": str(e)}
    return {"success": True, "pipeline": "vertical-cadastre-extraction", "persisted": persisted, "data": result}


@router.post("/ingest/point-cloud")
async def ingest_point_cloud(file: UploadFile = File(...), dataset_name: str = Form("user-upload"), _auth: TokenPayload = Depends(get_current_user_required)):
    """
    Ingests a real point-cloud asset (LAS/LAZ/CSV) into the platform uploads store
    and registers it as a runnable dataset for the VC-X pipeline. Provenance (SHA-256
    of the persisted bytes) is returned for audit-linking downstream.
    """
    import os
    import uuid
    from app.core.crypto import sha256_hash

    allowed = {".las", ".laz", ".csv", ".txt"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{ext or 'none'}'; allowed: {sorted(allowed)}")

    upload_root = "/app/data/uploads"
    ds_dir = os.path.join(upload_root, uuid.uuid4().hex)
    os.makedirs(ds_dir, exist_ok=True)
    dest = os.path.join(ds_dir, file.filename or f"upload{ext}")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")
    with open(dest, "wb") as f:
        f.write(content)

    digest = sha256_hash(content)
    return {
        "success": True,
        "dataset_id": os.path.basename(ds_dir),
        "dataset_name": dataset_name,
        "stored_path": dest,
        "bytes": len(content),
        "format": ext,
        "file_sha256": digest,
        "next_steps": [
            {"endpoint": "POST /api/v1/pipelines/vertical-cadastre/run", "param": "dataset_id"},
        ],
    }


@router.get("/runs")
async def get_pipeline_runs(limit: int = 10):
    """Returns recently persisted VC-X audit records (read from PostGIS)."""
    from sqlalchemy import select, desc
    from app.core.database import get_sessionmaker

    async def _query():
        from app.models.pipeline import PipelineRun, DatasetAsset

        async with get_sessionmaker()() as db:
            runs = (await db.execute(select(PipelineRun).order_by(desc(PipelineRun.created_at)).limit(limit))).scalars().all()
            out = []
            for r in runs:
                out.append({
                    "run_id": r.id,
                    "run_hash": r.run_hash,
                    "pipeline_id": r.pipeline_id,
                    "actor_id": r.actor_id,
                    "status": r.status,
                    "metrics": r.metrics,
                    "asset_id": r.asset_id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                })
            return out

    return await _query()


@router.get("/assets")
async def get_pipeline_assets():
    """Returns registered (persisted) dataset assets with their SHA-256 fingerprints."""
    from sqlalchemy import select, desc
    from app.core.database import get_sessionmaker

    async def _query():
        from app.models.pipeline import DatasetAsset

        async with get_sessionmaker()() as db:
            assets = (await db.execute(select(DatasetAsset).order_by(desc(DatasetAsset.registered_at)))).scalars().all()
            return [
                {
                    "asset_id": a.id,
                    "dataset_id": a.dataset_id,
                    "name": a.dataset_name,
                    "format": a.format,
                    "bytes": a.bytes,
                    "file_sha256": a.file_sha256,
                    "crs_epsg": a.crs_epsg,
                    "storage_path": a.storage_path,
                    "registered_at": a.registered_at.isoformat() if a.registered_at else None,
                }
                for a in assets
            ]

    return await _query()


@router.get("/presets/{pipeline_id}")
def get_pipeline_preset(pipeline_id: str):
    """
    Returns pre-configured demonstration presets for instant zero-friction execution in the Pipeline Studio.
    """
    catalog = {p["id"]: p for p in spatial_pipelines_registry.get_catalog()}
    if pipeline_id not in catalog:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found")
    
    pipeline_info = catalog[pipeline_id]
    preset_params = {
        param_name: spec["default"]
        for param_name, spec in pipeline_info.get("input_schema", {}).items()
    }
    return {
        "pipeline_id": pipeline_id,
        "preset_name": f"Airoli Sector 8 Hero Case — {pipeline_info['name']}",
        "default_parameters": preset_params
    }
