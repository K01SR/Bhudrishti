# Bhu-Drishti 3D — Product Overview

## 1. Vision & Core Mission
**Bhu-Drishti 3D** is a governed 3D cadastral and vertical property intelligence platform designed for India's National Land Records Modernisation Programme (Problem Statement SIH26011).

Unlike traditional 2D land registers or generic 3D city viewers, Bhu-Drishti 3D solves the multi-dimensional property challenge:
> **One property, full lifecycle, live: Multi-source evidence comes in $\rightarrow$ the system normalizes and analyzes it $\rightarrow$ AI/geometry constructs a 3D cadastral representation $\rightarrow$ PostGIS + topology rules validate it $\rightarrow$ an authorized district verifier inspects and approves it $\rightarrow$ the approved property becomes a tamper-evident spatial record $\rightarrow$ the public verifies a non-sensitive proof through QR codes.**

---

## 2. Key Differentiators
1. **Cadastral Registry vs. 3D Map:** The 3D map is merely the spatial user interface; the property registry, legal-geometric rules engine, and verification workflow are the actual core product.
2. **Official ULPIN Protection:** The parent official 14-character ULPIN (e.g., `12345678901234`) is preserved immutable. The child vertical identifier is strictly designated as **Proposed Bhu-Drishti 3D Spatial Extension**.
3. **Multi-Source Evidence Integration:** Synthesizes 6 distinct spatial inputs (GIS cadastre, multi-epoch UAV drone photogrammetry, airborne LiDAR, architectural CAD plans, continuous CORS GNSS, and DEM/DSM).
4. **Honest Algorithmic Quality:** No fabricated AI claims. Measured IoU, precision, recall, and floor-count accuracy are evaluated directly against known synthetic ground truth.
5. **Subterranean Clash Safety:** Identifies 3D spatial intersections between private building foundations (basements) and public infrastructure (stormwater pipes, metro tunnels).
6. **DPDP Compliance:** Public verification endpoints reveal cryptographic integrity without leaking sensitive citizen personal data or mortgage valuations.
