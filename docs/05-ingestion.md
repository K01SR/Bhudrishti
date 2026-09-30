# Bhu-Drishti 3D — Multi-Source Spatial Data Ingestion Pipeline

## 1. Supported Input Streams
Bhu-Drishti 3D visibly ingests 6 multi-source streams for the demonstration precinct:
1. **GIS Cadastral Layer:** GeoJSON (RFC 7946) base land parcels.
2. **UAV Photogrammetry (Epoch 1 & 2):** High-resolution Cloud-Optimized GeoTIFFs (COG).
3. **Classified LiDAR Point Cloud:** ASPRS LAS/LAZ 1.4 point clouds with returns (Ground=2, Building=6).
4. **Architectural Floor Plans:** AutoCAD DXF/DWG georeferenced sanction blueprints.
5. **CORS Differential GNSS Data:** Continuous CORS station differential corrections for centimeter-level accuracy.
6. **High-Resolution DEM / DSM:** 0.5m gridded digital elevation models referenced to Mean Sea Level (MSL).

---

## 2. Ingestion Stages & Integrity Checks
```text
UPLOAD
  ↓
FILE TYPE CHECK (MIME & Extension Security Guard)
  ↓
SIZE / SECURITY CHECK (Max 500MB per swath)
  ↓
METADATA EXTRACTION (Header Bounds, Sensor Class, Resolution)
  ↓
CRS REPROJECTION (Normalized into EPSG:7755 India National Grid)
  ↓
STORE ASSET IN MINIO S3 (Calculates SHA-256 Digest)
  ↓
REGISTER EVIDENCE ASSET (Tied to Parent Cadastral Parcel)
  ↓
CELERY ASYNC PROCESSING JOB DISPATCHED
```

---

## 3. Evidence Quality / Confidence Tier Classification
- **Tier A — Authoritative / Survey Grade:** SoI CORS, State Settlement Commissionerate GIS, calibrated LiDAR.
- **Tier B — Builder-Supplied / Professionally Verified:** Registered architect DWG drawings, licensed surveyor drone flights.
- **Tier C — Citizen-Declared:** Self-declared photos, possession certificates, citizen boundary requests.
