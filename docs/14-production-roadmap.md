# Bhu-Drishti 3D — Production Phase Roadmap

## 1. Post-Hackathon Phase 1: Statewide Scale (Months 1–3)
- **High-Throughput Spatial Partitioning:** Implement automated Uber H3 / S2 discrete global grid spatial indexing for multi-district parallel queries.
- **Enterprise IAM & Keycloak Integration:** Replace lightweight JWT authentication with OpenID Connect (OIDC) / SAML 2.0 federation with state single sign-on (SSO).
- **Official ULPIN Bureau Gateway:** Establish secure gRPC endpoints to sync directly with Department of Land Resources (DoLR) central ULPIN servers.

---

## 2. Phase 2: Autonomous Aerial Surveillance (Months 4–6)
- **Direct Drone Orthomosaic Tiling Service:** Ingest raw GeoTIFFs directly into dynamic Cloud-Optimized GeoTIFF (COG) / Slippy Map XYZ raster tile servers.
- **Automated AI Point Cloud Classification:** Transition from statistical thresholding to Deep Learning point cloud segmentation (PointNet++ / RandLA-Net) trained on Indian urban typologies.
- **BIM / IFC 4.3 Native Ingestion:** Direct parser for Industry Foundation Classes (IFC) architectural models into CityJSON and PostGIS PolyhedralSurfaces.

---

## 3. Phase 3: Statutory Blockchain / National Anchor (Months 7–12)
- **National Notary Anchor:** Periodically anchor the daily root hash of the tamper-evident audit chain onto India's National Blockchain Framework (NBF).
- **Automated Municipal Approval Gates:** Connect FSI auto-check engines directly to urban local body (ULB) building sanction software for real-time occupancy certificate approvals.
