# UI/UX Workflows, Ergonomics & User Journeys

> **Canonical System Reference:** [Master Monograph Chapter 17](../docs/00-master-system-documentation.md#17-frontend-component-architecture--design-system-tokens)  
> **Source Files:** [`frontend/src/components/layout/GlobalSearch.tsx`](../frontend/src/components/layout/GlobalSearch.tsx), [`frontend/src/pages/app/MapPage.tsx`](../frontend/src/pages/app/MapPage.tsx)

---

## 1. Ergonomic Spatial Interactions
* **Command Palette (`Ctrl+K` / `Cmd+K`):** Global instant search with recent searches, category filters (`All`, `Parcels`, `Buildings`, `Units`), and keyboard arrow navigation.
* **Spatial Inspector:** Floating translucent HUD docked cleanly to the viewport, preventing obstruction of Three.js controls.
* **Cinematic Drone Controls:** One-click automated aerial survey orbiting 360 degrees around the selected parcel at 300m elevation.
* **LiDAR Z-Plane Slice Bar:** Interactive slider isolating structural cross-sections and basement levels in real time.
