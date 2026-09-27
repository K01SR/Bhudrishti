from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class CanonicalParcel(BaseModel):
    parent_ulpin: str = Field(..., description="Official 14-character parent cadastral land parcel ULPIN")
    geometry_geojson: Dict[str, Any] = Field(..., description="2D GeoJSON polygon of parcel boundary")
    document_area_m2: float = Field(..., ge=0.0)
    calculated_area_m2: float = Field(..., ge=0.0)
    gis_area_m2: Optional[float] = None
    survey_number: Optional[str] = None
    jurisdiction_code: str


class CanonicalStructure(BaseModel):
    id: str = Field(..., description="Building structure code, e.g. B-17")
    name: str
    structure_type: str = "RESIDENTIAL_COMMERCIAL"
    footprint_geojson: Dict[str, Any] = Field(..., description="2D polygon of building footprint")
    ground_elevation_z: float = 0.0
    height_m: float = Field(..., gt=0.0)
    floors_count: int = Field(..., ge=1)
    basements_count: int = 0
    calculated_fsi: float = 0.0


class CanonicalVerticalUnit(BaseModel):
    unit_id: str = Field(..., description="e.g. 101, 201, 301, P01")
    proposed_3d_id: str = Field(..., description="Proposed Bhu-Drishti 3D Spatial ID")
    level_code: str
    floor_number: int
    unit_type: str = "U"
    min_z: float
    max_z: float
    carpet_area_m2: float
    built_up_area_m2: float
    volume_m3: float
    geometry_geojson: Dict[str, Any]
    mesh_geometry_3d: Optional[Dict[str, Any]] = None


class CanonicalSubsurfaceObject(BaseModel):
    code: str
    proposed_3d_id: str
    type_code: str = "X"
    description: str
    min_z: float
    max_z: float
    geometry_3d: Dict[str, Any]
    has_clash: bool = False
    clash_details: Optional[str] = None


class CanonicalEvidenceItem(BaseModel):
    source_type: str
    file_name: str
    file_hash: str
    storage_key: str
    confidence_tier: str
    quality_metric: Optional[float] = None
    timestamp: str


class CanonicalRight(BaseModel):
    unit_proposed_3d_id: str
    party_name: str
    party_type: str
    right_type: str
    share_pct: float = 100.0
    encumbrance_status: str = "ACTIVE"
    is_synthetic: bool = True


class CanonicalVerification(BaseModel):
    status: str
    case_number: Optional[str] = None
    verified_by: Optional[str] = None
    verification_date: Optional[str] = None
    digital_signature: Optional[str] = None
    geometry_fingerprint: Optional[str] = None
    public_qr_token: Optional[str] = None


class CanonicalPropertyRecord(BaseModel):
    schema_version: str = "1.0.0"
    specification: str = "Proposed Bhu-Drishti 3D Spatial Extension"
    disclaimer: str = "SYNTHETIC DEMO DATA — For technical evaluation of 3D Cadastral pipelines"
    parcel: CanonicalParcel
    structure: CanonicalStructure
    vertical_units: List[CanonicalVerticalUnit]
    subsurface_objects: List[CanonicalSubsurfaceObject] = []
    evidence: List[CanonicalEvidenceItem] = []
    rights: List[CanonicalRight] = []
    verification: CanonicalVerification


def get_canonical_json_schema() -> Dict[str, Any]:
    """Generates formal JSON Schema for Canonical Property Record."""
    return CanonicalPropertyRecord.model_json_schema()
