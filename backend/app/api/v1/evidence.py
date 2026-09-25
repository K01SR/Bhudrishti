from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from app.core.demo_gate import demo_mode_dependency, load_demo_dataset
from app.pipelines.floorplan_parser import floorplan_parser

router = APIRouter(prefix="/evidence", tags=["Multi-Source Spatial Evidence"])

_DATASET = load_demo_dataset()

# Multi-Source Evidence Streams.
#
# Every entry below previously carried `"available": True` together with an
# official-sounding provenance, a "Tier A - Authoritative Survey Grade" tier, a
# SHA-256 file hash, and a "PASSED" quality result carrying specific measured
# figures (0.02 m survey coordinate accuracy, 32.4 pts/m2 point density,
# 0.008 m horizontal RMS, a Riegl VUX-1LR sensor, an ASPRS class breakdown, an
# NMMC monitoring survey, and a detected "+3.5 m / added 6th floor"
# discrepancy).
#
# None of that data exists. The `file_hash` values are visibly hand-typed digit
# runs rather than digests of anything. There is no LiDAR flight, no
# orthomosaic, no CORS station, no NRSC DEM and no sanctioned drawing for this
# parcel in this repository. Claiming a Land Records Department source and a
# Tier A survey grade meant a fabricated government data lineage sat behind
# every downstream spatial number the UI showed.
#
# The catalogue is retained because the pipeline genuinely needs these streams,
# and a real one will eventually be ingested. Each entry is therefore marked
# unavailable, with the reason, and no accuracy, hash or pass/fail is asserted.

_NOT_OBTAINED = "Not obtained. No such file has been acquired for this parcel."

EVIDENCE_STREAMS = [
    {
        "id": "EV-01",
        "name": "GIS Cadastral Parcel Map",
        "source_type": "GIS_PARCEL",
        "available": False,
        "format": "GeoJSON (RFC 7946)",
        "crs": "EPSG:7755 (claimed; not verified)",
        "confidence_tier": "None",
        "provenance": "None. Not sourced from any authority.",
        "provenance_note": (
            "This previously claimed the Maharashtra Land Records Department / "
            "Settlement Commissionerate at Tier A survey grade. No cadastre was "
            "obtained. Only a hand-drawn demonstration footprint exists, and it "
            "is not a parcel boundary."
        ),
        "quality_result": "Not assessed. No data to assess.",
        "required_to_activate": (
            "An authorised cadastre extract for the parcel, with its issuing "
            "authority stated."
        ),
    },
    {
        "id": "EV-02",
        "name": "Aerial Orthomosaic (Epoch 1 baseline)",
        "source_type": "DRONE_EPOCH1",
        "available": False,
        "format": "Cloud-Optimized GeoTIFF (COG)",
        "confidence_tier": "None",
        "provenance": "None. No aerial survey was flown or obtained.",
        "provenance_note": (
            "Change detection needs two dated observations. Without this stream "
            "there is no baseline and therefore nothing to compare against."
        ),
        "quality_result": "Not assessed. No data to assess.",
        "required_to_activate": "An authenticated aerial survey upload for the parcel.",
    },
    {
        "id": "EV-03",
        "name": "Aerial Orthomosaic (Epoch 2 monitoring)",
        "source_type": "DRONE_EPOCH2",
        "available": False,
        "format": "Cloud-Optimized GeoTIFF (COG)",
        "confidence_tier": "None",
        "provenance": "None. Not a municipal monitoring survey.",
        "provenance_note": (
            "This previously claimed to be an NMMC survey and reported a "
            "'FLAGGED' structural discrepancy of +3.5 m and an added sixth "
            "floor. No municipal survey exists in this repository and no "
            "discrepancy has been detected. Reporting that finding would be an "
            "enforcement allegation about a real parcel with no evidence behind "
            "it."
        ),
        "quality_result": "Not assessed. No data to assess.",
        "required_to_activate": "A second, independently dated aerial observation.",
    },
    {
        "id": "EV-04",
        "name": "Classified LiDAR Point Cloud",
        "source_type": "LIDAR",
        "available": False,
        "format": "ASPRS LAS/LAZ 1.4",
        "confidence_tier": "None",
        "provenance": "None. No LiDAR survey was flown for this parcel.",
        "provenance_note": (
            "This previously named a specific airborne LiDAR sensor, a measured "
            "point density, and an ASPRS classification breakdown. No point "
            "cloud exists here, so any height derived from one would be "
            "invented."
        ),
        "quality_result": "Not assessed. No data to assess.",
        "required_to_activate": "A classified point cloud with its capture metadata.",
    },
    {
        "id": "EV-05",
        "name": "Architectural Sanction Floor Plans",
        "source_type": "FLOOR_PLAN",
        "available": False,
        "format": "AutoCAD DXF / DWG",
        "confidence_tier": "None",
        "provenance": "None. No sanctioned drawing is held.",
        "provenance_note": (
            "This previously cited a specific sanction application number and "
            "reported a verified storey count, basement and strata unit total. "
            "No sanction has been applied for, and the municipality has not "
            "approved anything here. A sanction reference is exactly the kind of "
            "detail that must not be invented."
        ),
        "quality_result": "Not assessed. No data to assess.",
        "required_to_activate": "A sanction drawing obtained from the applicant or the authority.",
    },
    {
        "id": "EV-06",
        "name": "CORS Continuous GNSS Reference",
        "source_type": "GNSS_CORS",
        "available": False,
        "format": "RINEX 3.04 / NMEA differential corrections",
        "confidence_tier": "None",
        "provenance": "None. Not connected to any reference station.",
        "provenance_note": (
            "This previously named a national CORS station and reported "
            "centimetre-level RMS residuals. No differential corrections were "
            "received, so no coordinate in this system is survey-grade."
        ),
        "quality_result": "Not assessed. No data to assess.",
        "required_to_activate": "Registered access to a geodetic reference station.",
    },
    {
        "id": "EV-07",
        "name": "High-Resolution DEM / DSM Elevation Model",
        "source_type": "DEM_DSM",
        "available": False,
        "format": "GeoTIFF elevation grid",
        "confidence_tier": "None",
        "provenance": "None. No elevation model was downloaded or used.",
        "provenance_note": (
            "This previously claimed a national remote-sensing centre DEM at a "
            "stated resolution on a stated vertical datum. Without a DEM, "
            "ground level and any height above datum are unknown."
        ),
        "quality_result": "Not assessed. No data to assess.",
        "required_to_activate": "A licensed elevation model for the region.",
    },
]

# The hashes were fabricated digit runs, not digests. Recomputing them over the
# catalogue above would lend the new entries a false air of having been
# verified, so they are reported as absent instead.
EVIDENCE_STREAMS_ARE_PLACEHOLDERS = True


@router.get("/")
def list_evidence(_guard: None = Depends(demo_mode_dependency)):
    """Lists all multi-source evidence streams ingested for the demo precinct."""
    return EVIDENCE_STREAMS


@router.get("/{stream_id}")
def get_evidence_stream(stream_id: str, _guard: None = Depends(demo_mode_dependency)):
    """Retrieves specific evidence stream metadata and provenance."""
    for s in EVIDENCE_STREAMS:
        if s["id"] == stream_id:
            return s
    raise HTTPException(status_code=404, detail=f"Evidence stream '{stream_id}' not found.")


# --------------------------------------------------------------------------- #
# Floor Plan Ingestion Endpoints (PS-26011 Core Requirement)                  #
# --------------------------------------------------------------------------- #

class ManualFloorPlanTraceRequest(BaseModel):
    unit_polygons: List[List[List[float]]] = Field(
        ...,
        description="List of 2D polygon rings [[[x1, y1], [x2, y2], ...], ...] representing unit footprints",
        example=[[[0.0, 0.0], [12.0, 0.0], [12.0, 10.0], [0.0, 10.0], [0.0, 0.0]]]
    )
    parent_ulpin: str = Field(default="12345678901234", description="Parent Land Parcel ULPIN")
    building_code: str = Field(default="B17", description="Building code identifier")
    level_code: str = Field(default="L01", description="Floor level code (e.g., L01, L02)")
    base_elevation_m: float = Field(default=3.6, description="Base floor level elevation above ground datum")
    floor_height_m: float = Field(default=3.6, description="Floor story height in meters")


@router.post("/floorplan/trace")
def ingest_manual_floorplan_trace(request: ManualFloorPlanTraceRequest):
    """
    Ingests manual vector traces or digitized floor plan polygons,
    extruding them into verified 3D strata solids with sub-ULPINs and volumes.
    """
    try:
        return floorplan_parser.parse_manual_trace(
            unit_polygons=request.unit_polygons,
            parent_ulpin=request.parent_ulpin,
            building_code=request.building_code,
            level_code=request.level_code,
            base_elevation_m=request.base_elevation_m,
            floor_height_m=request.floor_height_m
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Floor plan vector trace processing failed: {str(e)}")


@router.post("/floorplan/dxf")
async def ingest_dxf_floorplan(
    file: UploadFile = File(..., description="AutoCAD DXF architectural drawing file"),
    parent_ulpin: str = Form("12345678901234"),
    building_code: str = Form("B17"),
    level_code: str = Form("L01"),
    base_elevation_m: float = Form(3.6),
    floor_height_m: float = Form(3.6),
    unit_layer_prefix: Optional[str] = Form(None)
):
    """
    Ingests an AutoCAD DXF floor plan file, extracts closed polyline unit boundaries via ezdxf,
    scales to meters, and extrudes into 3D polyhedral strata units with 3D-ULPINs.
    """
    if not file.filename.lower().endswith(".dxf"):
        raise HTTPException(status_code=400, detail="Only .dxf architectural files are supported.")
    try:
        dxf_bytes = await file.read()
        return floorplan_parser.parse_dxf_bytes(
            dxf_bytes=dxf_bytes,
            parent_ulpin=parent_ulpin,
            building_code=building_code,
            level_code=level_code,
            base_elevation_m=base_elevation_m,
            floor_height_m=floor_height_m,
            unit_layer_prefix=unit_layer_prefix
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"DXF ingestion error: {str(e)}")
