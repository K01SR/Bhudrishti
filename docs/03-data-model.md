# Bhu-Drishti 3D — Core Data Model & Schema

## 1. Relational Entity-Relationship Structure
The platform implements a normalized relational schema with spatial geometry bindings:

### A. Administrative Hierarchy
- `jurisdictions`: State, District, Taluka, Village/Ward boundaries, center coordinates, and municipal rules (`max_fsi`).
- `parcels`: Official 14-character parent ULPIN, survey numbers, 2D boundary polygons, document area, calculated geometry area, and status.
- `structures`: Building code (`B-17`), footprint polygon, ground elevation $Z_0$, height ($m$), floors count, basements count, and calculated FSI.
- `levels`: Level code (`B1`, `G`, `L01`–`L05`), floor number, $[Z_{\min}, Z_{\max}]$ vertical intervals, and slab boundary geometry.
- `units`: Vertical unit code (`101`, `201`, `P01`), Proposed 3D ID, carpet area, built-up area, volume ($m^3$), 2D footprint, and 3D triangular mesh geometry.
- `spatial_units`: Specialized 3D volumetric entities: underground utility pipes (`PIPE-DRAIN-01`), transit tunnels (`METRO-LINE-2A`), elevated skywalks (`SKY1`), and vertical air-right columns (`AIR1`).

### B. Evidence & Quality Pipeline
- `evidence_sources`: Sensor types (`GIS_PARCEL`, `DRONE_EPOCH1`, `DRONE_EPOCH2`, `LIDAR`, `FLOOR_PLAN`, `GNSS_CORS`, `DEM_DSM`) and confidence tiers (Tier A/B/C).
- `evidence_assets`: File names, storage keys, SHA-256 file hashes, sizes, MIME types, CRS (`EPSG:7755`), and quality metrics.
- `submissions`: Contributor tracking (Builder, Citizen, Survey Officer), receipts, declared data, and lifecycle status.
- `processing_jobs`: Pipeline tasks, progress percentages, execution metrics, and logs.
- `derived_geometries`: Intermediate and final extracted features with method attribution and benchmark scores.

### C. Governance, QA & Cryptography
- `topology_issues`: Rules R001 through R016 findings, severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`), clash details, and recommended review actions.
- `verification_cases`: Verifier review queue, case numbers, priority, officer notes, and timestamps.
- `property_changes`: Temporal epoch differences, detected height increases, and volumetric deltas.
- `rights`: Land Title and encumbrance bindings (Ownership, Mortgage, Lease, Easement, Restriction) with party relationships.
- `property_versions`: Immutable version snapshots (V1, V2, V3) with SHA-256 fingerprints and Ed25519 digital signatures.
- `audit_events`: Tamper-evident hash chain linking $H_n = \text{SHA256}(H_{n-1} \parallel \text{CanonicalPayload}_n)$.
- `qr_tokens`: Public non-sensitive verification tokens with cryptographic proofs.
