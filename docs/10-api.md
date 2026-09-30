# Bhu-Drishti 3D — REST API Reference & Interoperability

## 1. Base URL & OpenAPI Specification
- **Base Endpoint:** `http://localhost:8000/api/v1`
- **Interactive Swagger Documentation:** `http://localhost:8000/docs`
- **Machine-Readable OpenAPI JSON:** `http://localhost:8000/openapi.json`

---

## 2. Core Endpoints Summary

### Authentication & RBAC
- `POST /auth/login`: Authenticate and receive JWT access token.
- `GET /auth/me`: Retrieve authenticated user profile and active role.
- `GET /auth/demo-accounts`: Pre-configured demo credentials for all roles.

### 3D Cadastral Properties & Parcels
- `GET /properties/hero`: Canonical Bhu-Drishti 3D model for Building B-17.
- `GET /properties/canonical-schema`: Formal Draft 2020-12 JSON Schema.
- `GET /parcels/`: List all 12 registered parcels in the precinct.
- `GET /parcels/geojson`: MapLibre GL compliant GeoJSON FeatureCollection.

### Multi-Source Spatial Evidence
- `GET /evidence/`: Ingested 6 spatial streams (GIS, Drone E1/E2, LiDAR, CAD, CORS, DEM).
- `GET /evidence/{stream_id}`: Detailed sensor provenance, CRS, and file hashes.

### Submissions & Pipeline Execution
- `GET /submissions/`: List submitted evidence packages.
- `POST /submissions/create`: Create new submission with tracking receipt.
- `POST /submissions/process-property`: Trigger automated 6-stage AI pipeline.

### Topology QA & Verification
- `GET /validation/run`: Execute rules R001 to R016 with clash reporting.
- `GET /validation/rules`: Full catalog of geometric and municipal rules.
- `GET /verification/cases`: Verifier queue of pending cadastral cases.
- `POST /verification/cases/{case_id}/decide`: Officer decision (`APPROVE`, `REJECT`, `CORRECTION_REQUESTED`).

### Multi-Epoch Temporal Changes
- `GET /changes/compare`: Differential volumetric analysis (2026 E1 vs 2027 E2).

### 3D ULPIN Engine
- `GET /ids/specification`: Official documentation of the proposed extension format.
- `POST /ids/generate`: Deterministic 3D ID generator with Luhn Mod 36 checksum.
- `GET /ids/decode`: Semantic parser, validator, and algorithm trace.

### Public QR Verification & Cryptography
- `GET /qr/verify/{token}`: DPDP-compliant non-sensitive public proof and Ed25519 signature check.
- `GET /qr/certificate/{token}`: Plain-text/JSON cadastral certificate.

### Interoperability Exports
- `GET /exports/cityjson`: OGC CityJSON 1.1 with LoD 2.0 MultiSurfaces.
- `GET /exports/geojson`: 2D GeoJSON boundary export.
- `GET /exports/canonical-json`: Full canonical Bhu-Drishti JSON export.
- `GET /exports/csv`: Tabular CSV summary of vertical units, volumes, and IDs.

### Ask-the-Map & Metrics
- `POST /queries/ask`: Natural-language spatial intent query parser.
- `GET /metrics/`: Measured algorithmic baselines vs synthetic ground truth.
- `GET /audit/events`: Tamper-evident SHA-256 hash-chain log.
- `GET /audit/verify-chain`: Verification of block-by-block cryptographic continuity.
