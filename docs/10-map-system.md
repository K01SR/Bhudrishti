# Unified Spatial Command Center & Map Modes

> **Canonical System Reference:** [Master Monograph Chapter 5](../docs/00-master-system-documentation.md#5-unified-spatial-command-center-map--3d-engine)  
> **Source Files:** [`frontend/src/pages/app/MapPage.tsx`](../frontend/src/pages/app/MapPage.tsx), [`frontend/src/components/openstudio/OpenTwinStudio.tsx`](../frontend/src/components/openstudio/OpenTwinStudio.tsx)  
> **Tests:** [`tests/test_api_endpoints.py:test_precinct_buildings_and_heatmap`](../tests/test_api_endpoints.py)

---

## 1. Unified Spatial Workspace

The `/app/map` workspace provides a single spatial inspection cockpit governed by the `?view={mode}` query parameter:
* **`open_twin`:** Live OpenStreetMap 3D reconstruction and instant 3D-ULPIN extrusion.
* **`3d`:** Multi-building precinct digital twin with typology-based rendering, FSI/Risk heatmaps, and a 12-second drone flyover camera interpolation.
* **`lidar`:** High-speed vectorized LiDAR workstation with Z-plane slicing and elevation gradient colormaps.
* **`cadastre`:** All-India 2D Cadastre Atlas powered by MapLibre GL 4.5.
* **`satellite`:** Esri World Imagery (0.3m/pixel) orthophotography basemap, served from the public Esri tile endpoint. No API key required.

### Basemap tile sources and the CARTO key

The `open_twin` and `cadastre` views share CARTO raster basemaps (`dark_all` and
`light_all`). Every other source in the project is still keyless: Esri World
Imagery, AWS Terrain Tiles, EOX Sentinel-2 cloudless, and the Overpass API.

CARTO is the exception, and it is worth being precise about why. CARTO now
requires a key for raster basemaps, supplied as `VITE_CARTO_API_KEY` in
`frontend/.env` (gitignored; see `frontend/.env.example`). The keyless failure
mode is the reason this is documented rather than left to discovery: a keyless
request still returns **HTTP 200 and a valid PNG**, but the image is a flat grey
placeholder that is **byte-identical for every coordinate**. Verified against
this project's own tile coordinates: the keyless response hashes the same at
z13 and z14 and across adjacent `x` values, while keyed responses differ per
coordinate and carry real map detail. So an unkeyed build renders a blank
viewport and reports no error anywhere.

Two things follow, and they are separate:

* **The key must stay out of git.** It goes in `frontend/.env` only. Vite inlines
  `VITE_*` variables into the client bundle, so the value is readable from
  devtools — that is expected for a raster basemap key and is why CARTO
  publishes rather than hides them. The real control is a domain restriction on
  the key in CARTO's dashboard, not secrecy.
* **The `© OpenStreetMap contributors © CARTO` credit must stay visible.**
  Adding a key does not discharge the ODbL or CARTO's attribution terms, and
  CARTO's own key email asks for the credit to remain.

Enforced by `tests/test_carto_basemap_key.py`, which scans every non-ignored
file for a `cb1_…` key, asserts both basemaps route through the `cartoTile()`
helper, and pins the keyless-placeholder behaviour so the key cannot be
"simplified" away without a test failing.
