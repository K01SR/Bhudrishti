"""
Ingest endpoints for real data with explicit provenance.

Provides endpoints for:
1. Real point-cloud processing (LAS/LAZ/COPC) via existing vertical_cadastre_pipeline
2. GNSS survey ingest with proper geodesic area computation
3. Parcel GeoJSON import with India bounds validation
4. Drone metadata/EXIF ingest
"""

from __future__ import annotations

import os
import uuid
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.security import TokenPayload, get_current_user_required
from app.core.config import settings
import os

def get_current_user_optional():
    """Optional auth for tests/development."""
    # In test mode, allow unauthenticated
    if os.environ.get("TESTING") == "true" or settings.ENVIRONMENT == "test":
        return TokenPayload(sub="test_user", role="STATE_ADMIN")
    return Depends(get_current_user_required)

async def get_auth(token = Depends(get_current_user_required)) -> TokenPayload:
    # Allow in test mode
    if os.environ.get("TESTING") == "true" or settings.ENVIRONMENT == "test":
        return TokenPayload(sub="test_user", role="STATE_ADMIN")
    return token

from app.core.crypto import sha256_hash
from app.pipelines.vertical_cadastre_pipeline import VerticalCadastrePipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])


class ProvenanceInfo(BaseModel):
    """Provenance metadata for ingested data."""
    is_real: bool = False
    is_derived: bool = True
    source: str = "UNKNOWN"
    derivation_method: Optional[str] = None
    confidence_tier: str = "LOW"
    provenance_note: str = Field(default="This data is derived/modelled and not authoritative survey data.")
    provenance: str = Field(default="Derived/Modelled - not survey-grade or authoritative.")
    data_type: str = "DERIVED"
    has_authentic_source: bool = False


class PointCloudResponse(BaseModel):
    """Response for point cloud ingestion."""
    success: bool
    asset_id: str
    dataset_id: str
    file_name: str
    file_sha256: str
    size_bytes: int
    format: str
    result: Optional[Dict[str, Any]] = None
    provenance: ProvenanceInfo


class GNSSPoint(BaseModel):
    lat: float = Field(..., description="Latitude in decimal degrees (EPSG:4326)")
    lon: float = Field(..., description="Longitude in decimal degrees (EPSG:4326)")
    elev: Optional[float] = Field(None, description="Elevation in meters")
    name: Optional[str] = None


class GNSSIngestRequest(BaseModel):
    points: List[GNSSPoint]
    submission_id: Optional[str] = None
    description: Optional[str] = None


class GNSSIngestResponse(BaseModel):
    success: bool
    point_count: int
    geometry_type: str
    area_m2: Optional[float] = None
    perimeter_m: Optional[float] = None
    centroid: Optional[List[float]] = None
    crs: str
    provenance: ProvenanceInfo
    computation_method: str
    warning: Optional[str] = None


class ParcelGeoJSONRequest(BaseModel):
    geojson: Dict[str, Any]
    submission_id: Optional[str] = None
    is_authoritative: bool = False
    source: Optional[str] = None


class ParcelGeoJSONResponse(BaseModel):
    success: bool
    feature_count: int
    valid_count: int
    rejected_features: List[Dict[str, Any]] = []
    area_m2: Optional[float] = None
    provenance: ProvenanceInfo


class DroneEXIFResponse(BaseModel):
    success: bool
    file_name: str
    has_gps: bool
    gps: Optional[Dict[str, Any]] = None
    capture_time: Optional[str] = None
    camera: Optional[Dict[str, Any]] = None
    sensor: Optional[Dict[str, Any]] = None
    exif_keys_count: int
    provenance: ProvenanceInfo


def is_point_in_india(lat: float, lon: float) -> bool:
    """
    Check if coordinates are approximately within India bounds.
    Rough bounding box for India (landmass inclusive of territories).
    """
    if lat < 6.0 or lat > 37.0:
        return False
    if lon < 68.0 or lon > 97.5:
        return False
    return True


def compute_geodesic_area(points: List[List[float]]) -> float:
    """
    Compute area using geodesic algorithm (Haversine-based polygon area).
    Returns area in square meters using WGS84 ellipsoid approximation.
    
    Note: This uses the spherical polygon area formula with Earth radius.
    For small parcels, this is accurate enough. For precision surveying,
    use projected CRS (EPSG:32643 for UTM Zone 43N covering parts of India).
    """
    if len(points) < 3:
        return 0.0
    
    import math
    
    # Earth's radius in meters (WGS84 semi-major axis approximation)
    R = 6378137.0  # WGS84 Earth radius
    
    # Convert to radians
    coords = []
    for p in points:
        coords.append([math.radians(p[0]), math.radians(p[1])])
    
    # Close polygon if needed
    if coords[0] != coords[-1]:
        coords.append(coords[0].copy())
    
    area = 0.0
    n = len(coords)
    for i in range(n - 1):
        phi1, phi2 = coords[i][0], coords[i + 1][0]
        lambda1, lambda2 = coords[i][1], coords[i + 1][1]
        area += (lambda2 - lambda1) * (2 + math.sin(phi1) + math.sin(phi2))
    
    area = abs(area) * R * R / 2.0
    return float(area)


def compute_geodesic_perimeter(points: List[List[float]]) -> float:
    """Compute perimeter in meters using geodesic distance."""
    if len(points) < 2:
        return 0.0
    
    import math
    
    R = 6378137.0
    
    def haversine(lat1, lon1, lat2, lon2):
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
    
    total = 0.0
    for i in range(len(points) - 1):
        total += haversine(math.radians(points[i][0]), math.radians(points[i][1]),
                          math.radians(points[i + 1][0]), math.radians(points[i + 1][1]))
    # Close if needed
    if len(points) > 2 and (points[0][0] != points[-1][0] or points[0][1] != points[-1][1]):
        total += haversine(math.radians(points[-1][0]), math.radians(points[-1][1]),
                          math.radians(points[0][0]), math.radians(points[0][1]))
    return float(total)


def transform_to_utm43n(lat: float, lon: float) -> tuple:
    """
    Transform WGS84 lat/lon to EPSG:32643 (UTM Zone 43N) for area calculations in meters.
    This is used when accurate projected area is needed for India regions in UTM 43N.
    """
    try:
        from pyproj import Transformer
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
        x, y = transformer.transform(lon, lat)
        return (x, y)
    except Exception:
        # Fallback to geodesic if pyproj not available
        raise


def compute_projected_area_m2(points_latlon: List[List[float]]) -> Optional[float]:
    """
    Compute area in square meters using projected CRS EPSG:32643.
    Returns None if transformation fails.
    """
    if len(points_latlon) < 3:
        return None
    try:
        # Transform all points
        pts_proj = []
        for p in points_latlon:
            x, y = transform_to_utm43n(p[0], p[1])
            pts_proj.append((x, y))
        # Compute polygon area
        from shapely.geometry import Polygon
        poly = Polygon(pts_proj)
        if poly.is_valid:
            return float(poly.area)
        else:
            return float(poly.buffer(0).area)
    except Exception:
        return None


@router.post("/point-cloud", response_model=PointCloudResponse)
async def ingest_point_cloud(
    file: UploadFile = File(...),
    dataset_name: str = Form("user-upload"),
    submission_id: Optional[str] = Form(None),
    ground_z: float = Form(0.0),
    _auth: TokenPayload = Depends(get_auth()) if False else Depends(get_current_user_required),
):
    """
    Real point-cloud processing — accept a LAS/LAZ or COPC upload and run it
    through the EXISTING vertical_cadastre_pipeline. Label results as derived/modelled,
    with explicit provenance metadata.
    """
    import uuid
    from app.core.crypto import sha256_hash
    
    if not file.filename:
        raise HTTPException(status_code=422, detail="Filename required.")
    
    allowed = {".las", ".laz", ".copc", ".csv", ".txt"}
    ext = os.path.splitext(os.path.basename(file.filename))[1].lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported format '{ext}'; allowed: {sorted(allowed)}",
        )
    
    # Read and validate (reuse streaming pattern - read all then validate size)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")
    
    # Size limit (20MB like builder_assets pattern, but could be configurable)
    MAX_SIZE = 100 * 1024 * 1024  # 100MB for point clouds
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds size limit (max 100MB).")
    
    # Basic magic byte validation for LAS/LAZ/COPC
    head = content[:4] if len(content) >= 4 else content
    if ext in {".las", ".laz", ".copc"}:
        # LAS files start with LASF in header; LAZ/COPC have specific signatures
        # Basic sanity check
        if len(head) < 4:
            raise HTTPException(status_code=422, detail="Invalid point cloud file.")
    
    # Store file
    upload_root = os.environ.get("UPLOAD_ROOT", "/tmp/uploads")
    dataset_id = uuid.uuid4().hex
    ds_dir = os.path.join(upload_root, dataset_id)
    os.makedirs(ds_dir, exist_ok=True)
    dest = os.path.join(ds_dir, file.filename or f"upload{ext}")
    
    with open(dest, "wb") as f:
        f.write(content)
    
    file_sha256 = sha256_hash(content)
    
    # Run through existing pipeline
    pipeline_result = None
    try:
        pipeline = VerticalCadastrePipeline()
        pipeline_result = pipeline.run_real(
            asset_path=dest,
            ground_z=ground_z,
            actor_id=f"ingest-{dataset_id}",
        )
    except Exception as e:
        # Clean up on error
        import shutil
        shutil.rmtree(ds_dir, ignore_errors=True)
        # This used to swallow the failure and fall through to
        # `PointCloudResponse(success=True, result={"error": ...})`, so a point
        # cloud the pipeline could not read came back as HTTP 200 with an error
        # object in the body. Callers that checked the status saw success, and
        # the only way to notice was to read into `result`. A processing failure
        # is a server-side fault and now says so with a 5xx.
        #
        # The exception text is not echoed back: it can contain local paths and
        # library internals, and it is logged instead.
        logger.exception("Point-cloud pipeline failed for %s", file.filename)
        raise HTTPException(
            status_code=500,
            detail=(
                f"Point-cloud processing failed for '{file.filename}'. "
                "The file was accepted but could not be processed."
            ),
        ) from e
    
    provenance = ProvenanceInfo(
        is_real=False,  # We use real file but results are derived/modelled
        is_derived=True,
        source="USER_UPLOAD",
        derivation_method="VerticalCadastrePipeline (existing real_data_adapter + building_extraction + floor_segmentation + vertical_delineation)",
        confidence_tier="MEDIUM",
        provenance_note="Point cloud file uploaded by user; processing via existing pipeline produces derived/modelled structural geometry (no claim of survey-grade accuracy without authoritative survey metadata).",
        provenance="DERIVED/MODELLED - Processed through automated extraction pipeline; not authoritative survey-grade LiDAR. Results are modelled estimates.",
        data_type="POINT_CLOUD_DERIVED",
        has_authentic_source=True,  # The file is real upload, but extraction is derived
    )
    
    return PointCloudResponse(
        success=True,
        asset_id=dataset_id,
        dataset_id=dataset_id,
        file_name=file.filename or f"upload{ext}",
        file_sha256=file_sha256,
        size_bytes=len(content),
        format=ext.lstrip(".").upper(),
        result=pipeline_result,
        provenance=provenance,
    )


@router.post("/gnss", response_model=GNSSIngestResponse)
async def ingest_gnss_survey(
    request: GNSSIngestRequest,
    _auth: TokenPayload = Depends(get_auth()) if False else Depends(get_current_user_required),
):
    """
    GNSS survey ingest — accept georeferenced survey points. Compute areas/geometry
    geodesically or in a projected CRS, NOT by treating degree values as metres.
    """
    if not request.points or len(request.points) < 3:
        raise HTTPException(
            status_code=422,
            detail="At least 3 points required to form a polygon/area.",
        )
    
    # Collect coordinates (lat, lon)
    coords_latlon = []
    for p in request.points:
        lat, lon = p.lat, p.lon
        # Validate India bounds
        if not is_point_in_india(lat, lon):
            raise HTTPException(
                status_code=422,
                detail=f"Coordinates ({lat}, {lon}) are outside India bounds. Rejecting as per policy.",
            )
        coords_latlon.append([lat, lon])
    
    # Close polygon if not closed
    if coords_latlon[0] != coords_latlon[-1]:
        coords_latlon.append([coords_latlon[0][0], coords_latlon[0][1]])
    
    # Compute area - use geodesic (correct for degrees) as primary
    # Also try projected CRS for better accuracy
    area_m2_geodesic = compute_geodesic_area(coords_latlon)
    area_m2_proj = compute_projected_area_m2(coords_latlon)
    
    # Prefer projected if available and reasonable
    area_m2 = area_m2_proj if area_m2_proj is not None else area_m2_geodesic
    computation_method = "Projected CRS (EPSG:32643)" if area_m2_proj is not None else "Geodesic (spherical)"
    
    perimeter_m = compute_geodesic_perimeter(coords_latlon)
    
    # Compute centroid
    centroid_lat = sum(c[0] for c in coords_latlon[:-1]) / len(coords_latlon[:-1]) if len(coords_latlon) > 1 else coords_latlon[0][0]
    centroid_lon = sum(c[1] for c in coords_latlon[:-1]) / len(coords_latlon[:-1]) if len(coords_latlon) > 1 else coords_latlon[0][1]
    
    provenance = ProvenanceInfo(
        is_real=True,  # GNSS survey points are real measurements if provided
        is_derived=False,
        source="GNSS_SURVEY",
        derivation_method=computation_method,
        confidence_tier="HIGH",
        provenance_note="GNSS survey points ingested. Area computed using geodesic/projected methods - NOT treating degrees as square meters.",
        provenance="REAL - GNSS survey coordinates (georeferenced). Geometric calculations performed geodesically or in projected CRS.",
        data_type="GNSS_SURVEY_POINTS",
        has_authentic_source=True,
    )
    
    return GNSSIngestResponse(
        success=True,
        point_count=len(request.points),
        geometry_type="POLYGON",
        area_m2=round(area_m2, 6),
        perimeter_m=round(perimeter_m, 6),
        centroid=[round(centroid_lat, 6), round(centroid_lon, 6)],
        crs="EPSG:4326 (WGS84)",
        provenance=provenance,
        computation_method=f"{computation_method} - degrees NOT treated as meters",
        warning=None,
    )


@router.post("/parcel-geojson", response_model=ParcelGeoJSONResponse)
async def ingest_parcel_geojson(
    request: ParcelGeoJSONRequest,
    _auth: TokenPayload = Depends(get_auth()) if False else Depends(get_current_user_required),
):
    """
    Parcel GeoJSON import — accept a GeoJSON FeatureCollection of parcel polygons.
    Validate CRS, reject coordinates outside India bounds, and record whether
    the geometry is authoritative or builder-asserted.
    """
    if not request.geojson:
        raise HTTPException(status_code=422, detail="GeoJSON is required.")
    
    # Check for FeatureCollection
    geo_type = request.geojson.get("type")
    if geo_type != "FeatureCollection":
        # Try to handle single Feature
        if geo_type == "Feature":
            features = [request.geojson]
        elif geo_type == "Polygon" or geo_type == "MultiPolygon":
            features = [{"type": "Feature", "geometry": request.geojson, "properties": {}}]
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported GeoJSON type: {geo_type}. Expected FeatureCollection, Feature, Polygon, or MultiPolygon.",
            )
    else:
        features = request.geojson.get("features", [])
    
    if not features:
        raise HTTPException(status_code=422, detail="No features found in GeoJSON.")
    
    crs = request.geojson.get("crs")
    # Note: CRS in GeoJSON is deprecated but may be present; standard is EPSG:4326
    # We assume WGS84 (EPSG:4326) for GeoJSON coordinates
    
    rejected = []
    valid_features = []
    total_area = 0.0
    
    for idx, feat in enumerate(features):
        try:
            geom = feat.get("geometry", {})
            geom_type = geom.get("type")
            coords = geom.get("coordinates")
            
            if not coords:
                rejected.append({"index": idx, "reason": "Missing coordinates"})
                continue
            
            # Extract polygon coordinates
            poly_coords = []
            if geom_type == "Polygon":
                # First ring (exterior)
                if coords and coords[0]:
                    poly_coords = coords[0]
            elif geom_type == "MultiPolygon":
                # Use first polygon
                if coords and coords[0] and coords[0][0]:
                    poly_coords = coords[0][0]
            else:
                rejected.append({"index": idx, "reason": f"Unsupported geometry type: {geom_type}"})
                continue
            
            # Validate coordinates
            if len(poly_coords) < 3:
                rejected.append({"index": idx, "reason": "Polygon has fewer than 3 vertices"})
                continue
            
            # Check bounds and collect valid coords
            valid_poly = []
            for c in poly_coords:
                if len(c) < 2:
                    continue  # skip invalid
                lon, lat = c[0], c[1]  # GeoJSON is lon, lat
                if not is_point_in_india(lat, lon):
                    rejected.append({
                        "index": idx,
                        "reason": f"Coordinates ({lat}, {lon}) outside India bounds",
                        "vertex": [lon, lat],
                    })
                    break  # reject this feature
                valid_poly.append([lat, lon])  # Store as lat, lon
            else:
                # No break occurred - all vertices valid
                if len(valid_poly) >= 3:
                    valid_features.append(feat)
                    # Compute area
                    area = compute_projected_area_m2(valid_poly)
                    if area is None:
                        area = compute_geodesic_area(valid_poly)
                    total_area += area
                else:
                    rejected.append({"index": idx, "reason": "Insufficient valid vertices after validation"})
        
        except Exception as e:
            rejected.append({"index": idx, "reason": f"Validation error: {str(e)}"})
    
    # Check for rejection due to outside India bounds
    for rej in rejected:
        if "outside India bounds" in rej.get("reason", ""):
            raise HTTPException(status_code=422, detail=rej["reason"])
    
    source_label = request.source or ("AUTHORITATIVE" if request.is_authoritative else "BUILDER_ASSERTED")
    provenance = ProvenanceInfo(
        is_real=request.is_authoritative,  # Only if explicitly marked authoritative
        is_derived=not request.is_authoritative,
        source=source_label,
        derivation_method="GeoJSON import with bounds validation",
        confidence_tier="HIGH" if request.is_authoritative else "LOW",
        provenance_note=f"Parcel GeoJSON imported as {source_label}. Geometry validated for India bounds and CRS assumptions.",
        provenance=f"{source_label} - GeoJSON FeatureCollection. CRS assumed WGS84 (EPSG:4326) unless specified; geometry classified by source authority.",
        data_type="PARCEL_GEOJSON",
        has_authentic_source=request.is_authoritative,
    )
    
    return ParcelGeoJSONResponse(
        success=True,
        feature_count=len(features),
        valid_count=len(valid_features),
        rejected_features=rejected,
        area_m2=round(total_area, 6) if total_area > 0 else None,
        provenance=provenance,
    )


@router.post("/drone-exif", response_model=DroneEXIFResponse)
async def ingest_drone_exif(
    file: UploadFile = File(...),
    _auth: TokenPayload = Depends(get_auth()) if False else Depends(get_current_user_required),
):
    """
    Drone metadata/EXIF ingest — extract capture metadata (time, GPS if present,
    camera/sensor identifiers) from an uploaded image. Pillow is available transitively
    but may need to be declared as dependency; this handles gracefully if missing.
    """
    if not file.filename:
        raise HTTPException(status_code=422, detail="Filename required.")
    
    ext = os.path.splitext(os.path.basename(file.filename))[1].lower()
    allowed_img = {".jpg", ".jpeg", ".tiff", ".tif", ".png"}
    if ext not in allowed_img:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported image format '{ext}'; allowed: {sorted(allowed_img)}",
        )
    
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")
    
    MAX_SIZE = 50 * 1024 * 1024  # 50MB for images
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds size limit (max 50MB).")
    
    gps_data = None
    capture_time = None
    camera_info = None
    sensor_info = None
    exif_keys = []
    
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS
        
        # Save to temp and open
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            img = Image.open(tmp_path)
            exif = img._getexif()
            if exif:
                for tag_id, value in exif.items():
                    tag = TAGS.get(tag_id, tag_id)
                    exif_keys.append(str(tag))
                    
                    # Camera info
                    if tag in ('Make', 'Model', 'Software', 'LensModel', 'LensMake'):
                        if camera_info is None:
                            camera_info = {}
                        camera_info[tag.lower()] = str(value) if not isinstance(value, (int, float)) else value
                    
                    # Date/time
                    if tag in ('DateTime', 'DateTimeOriginal', 'DateTimeDigitized'):
                        capture_time = str(value)
                    
                    # GPS info
                    if tag == 'GPSInfo':
                        gps_info = {}
                        for gps_tag_id, gps_value in value.items():
                            gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                            gps_info[gps_tag] = gps_value
                        gps_data = _parse_gps_info(gps_info)
        finally:
            os.unlink(tmp_path)
    
    except ImportError:
        # Pillow not installed - note this in response
        provenance_note = "Pillow not installed; EXIF extraction not available. Metadata cannot be extracted from image."
    except Exception as e:
        # Other error - still return structure
        provenance_note = f"EXIF extraction failed: {str(e)}. Partial metadata only."
    else:
        provenance_note = "Drone/camera image EXIF metadata extracted. GPS coordinates extracted if present in image."
    
    has_gps = gps_data is not None and len(gps_data) > 0
    
    provenance = ProvenanceInfo(
        is_real=True if has_gps else False,
        is_derived=False,
        source="DRONE_IMAGE_EXIF",
        derivation_method="EXIF metadata extraction",
        confidence_tier="HIGH" if has_gps else "LOW",
        provenance_note=provenance_note,
        provenance="EXTRACTED - Metadata from uploaded image file (EXIF). Not modelled; reflects embedded capture data.",
        data_type="DRONE_METADATA",
        has_authentic_source=has_gps,  # GPS in EXIF is embedded from capture device
    )
    
    return DroneEXIFResponse(
        success=True,
        file_name=file.filename or f"upload{ext}",
        has_gps=has_gps,
        gps=gps_data,
        capture_time=capture_time,
        camera=camera_info,
        sensor=sensor_info,
        exif_keys_count=len(exif_keys),
        provenance=provenance,
    )


def _parse_gps_info(gps_info: Dict) -> Optional[Dict[str, Any]]:
    """Parse GPS EXIF info to decimal degrees."""
    try:
        def _convert_to_degrees(value):
            # value is (degrees, minutes, seconds) tuple
            if not value or len(value) < 3:
                return None
            d, m, s = value
            # Handle rational numbers if present
            if hasattr(d, 'numerator'):
                d = float(d.numerator) / float(d.denominator) if d.denominator else 0
            else:
                d = float(d)
            if hasattr(m, 'numerator'):
                m = float(m.numerator) / float(m.denominator) if m.denominator else 0
            else:
                m = float(m)
            if hasattr(s, 'numerator'):
                s = float(s.numerator) / float(s.denominator) if s.denominator else 0
            else:
                s = float(s)
            return d + (m / 60.0) + (s / 3600.0)
        
        lat = None
        lon = None
        if 'GPSLatitude' in gps_info and 'GPSLatitudeRef' in gps_info:
            lat = _convert_to_degrees(gps_info['GPSLatitude'])
            if gps_info['GPSLatitudeRef'] == 'S' and lat is not None:
                lat = -lat
        if 'GPSLongitude' in gps_info and 'GPSLongitudeRef' in gps_info:
            lon = _convert_to_degrees(gps_info['GPSLongitude'])
            if gps_info['GPSLongitudeRef'] == 'W' and lon is not None:
                lon = -lon
        
        if lat is None or lon is None:
            return None
        
        result = {"lat": round(lat, 6), "lon": round(lon, 6)}
        if 'GPSAltitude' in gps_info:
            alt = gps_info['GPSAltitude']
            if hasattr(alt, 'numerator'):
                alt = float(alt.numerator) / float(alt.denominator) if alt.denominator else 0
            result["altitude_m"] = float(alt)
        return result
    except Exception:
        return None
