from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.jurisdictions import router as jurisdictions_router
from app.api.v1.parcels import router as parcels_router
from app.api.v1.properties import router as properties_router
from app.api.v1.evidence import router as evidence_router
from app.api.v1.submissions import router as submissions_router
from app.api.v1.validation import router as validation_router
from app.api.v1.verification import router as verification_router
from app.api.v1.rights import router as rights_router
from app.api.v1.changes import router as changes_router
from app.api.v1.ids import router as ids_router
from app.api.v1.qr import router as qr_router
from app.api.v1.exports import router as exports_router
from app.api.v1.ask_map import router as ask_map_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.audit import router as audit_router
from app.api.v1.demo import router as demo_router
from app.api.v1.pipelines_api import router as pipelines_router
from app.api.v1.search import router as search_router
from app.api.v1.lidar import router as lidar_router
from app.api.v1.lidar_inspect import router as lidar_inspect_router
from app.api.v1.integrity import router as integrity_router
from app.api.v1.objections import router as objections_router
from app.api.v1.precinct import router as precinct_router
from app.api.v1.builder_submissions import router as builder_submissions_router
from app.api.v1.builder_assets import router as builder_assets_router, files_router as assets_files_router
from app.api.v1.locations import router as locations_router
from app.api.v1.datasources import router as datasources_router
from app.api.v1.dilrmp import router as dilrmp_router
from app.api.v1.system_router import router as system_router
from app.api.v1.osm import router as osm_router
from app.api.v1.blockchain_api import router as blockchain_router
from app.api.v1.opendata import router as opendata_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(jurisdictions_router)
api_router.include_router(parcels_router)
api_router.include_router(properties_router)
api_router.include_router(evidence_router)
api_router.include_router(submissions_router)
api_router.include_router(validation_router)
api_router.include_router(verification_router)
api_router.include_router(rights_router)
api_router.include_router(changes_router)
api_router.include_router(ids_router)
api_router.include_router(qr_router)
api_router.include_router(exports_router)
api_router.include_router(ask_map_router)
api_router.include_router(metrics_router)
api_router.include_router(audit_router)
api_router.include_router(demo_router)
api_router.include_router(pipelines_router)
api_router.include_router(search_router)
api_router.include_router(lidar_router)
api_router.include_router(lidar_inspect_router)
api_router.include_router(integrity_router)
api_router.include_router(objections_router)
api_router.include_router(precinct_router)
api_router.include_router(builder_submissions_router)
api_router.include_router(builder_assets_router)
api_router.include_router(assets_files_router)
api_router.include_router(locations_router)
api_router.include_router(datasources_router)
api_router.include_router(dilrmp_router)
api_router.include_router(system_router)
api_router.include_router(osm_router)
api_router.include_router(blockchain_router)
api_router.include_router(opendata_router)


from app.api.v1.ingest import router as ingest_router
api_router.include_router(ingest_router)
