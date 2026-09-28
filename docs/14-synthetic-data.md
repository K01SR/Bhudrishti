# Bhu-Drishti 3D — Synthetic Airoli Demo Dataset & Ground Truth

## 1. Context & Purpose
To guarantee reproducible evaluation for hackathon juries without requiring proprietary commercial survey datasets, Bhu-Drishti 3D provides a **programmatically synthesized 400m $\times$ 400m urban precinct in Airoli Sector 8, Navi Mumbai**.

> **SYNTHETIC DEMO DISCLAIMER:**  
> This dataset contains synthetic demo data for technical evaluation of 3D spatial algorithms, not official government revenue records.

---

## 2. Dataset Geographic Parameters
- **Geographic Center:** Airoli Sector 8, Navi Mumbai ($19.1557^\circ\text{ N}, 72.9984^\circ\text{ E}$).
- **Local Bounding Grid:** $400\text{m} \times 400\text{m}$ grid $[0, 400] \times [0, 400]$.
- **Projected Coordinate Reference System:** **EPSG:7755** (India National Grid).
- **Vertical Datum:** Mean Sea Level (MSL), meters.

---

## 3. Hero Feature: Building B-17
- **Parent Cadastral Parcel:** `12345678901234` (Plot area: $1,000.0\text{ m}^2$, coordinates $[140, 140]$ to $[180, 165]$).
- **Ground Footprint:** $510.0\text{ m}^2$ ($30\text{m} \times 17\text{m}$ setback envelope).
- **Structure Envelope:** Height $18.0\text{m}$, 5 Above-Ground Floors, 1 Basement.
- **Vertical Units (21 Units Total):**
  - 1 Basement Parking Slot (Unit `P01`, Type P, $Z \in [-3.5\text{m}, 0.0\text{m}]$).
  - 5 Residential Floors $\times$ 4 Units per floor = 20 Apartments (Units `101-104`, `201-204`, `301-304`, `401-404`, `501-504`).
  - Hero Apartment Unit: `201` (`12345678901234/UB17-L02-201-X`) on Level 2 with active SBI mortgage.
- **Subterranean Infrastructure:**
  - Municipal Stormwater Drainage Main (`PIPE-DRAIN-01`, Type X, $Z \in [-3.8\text{m}, -3.0\text{m}]$) intersecting basement foundation at $Z = -3.2\text{m}$ (CLASH!).
  - Deep Metro Line 2A Tunnel at $Z = -10.0\text{m}$.
- **Elevated & Air Rights:**
  - Elevated Pedestrian Skywalk (`SKY1`, Type E, Level 3, $Z \in [10.8\text{m}, 14.4\text{m}]$).
  - Vertical Air-Right Column (`AIR1`, Type A, Level 10, $Z \in [18.0\text{m}, 30.0\text{m}]$).
