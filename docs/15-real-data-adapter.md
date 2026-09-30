# Bhu-Drishti 3D — Real Open-Source Data Adapter

## 1. Context & Purpose
In addition to the synthetic Airoli demo dataset, Bhu-Drishti 3D implements a dedicated adapter to ingest and process real, publicly available airborne point cloud datasets (in standard ASPRS `.las` / `.laz` format) using `laspy` and NumPy.

---

## 2. Requirements & Standards
- **License Tracking:** Explicitly preserves source provenance and open data licenses (e.g. Open Government License - OGL, CC-BY 4.0, USGS 3DEP).
- **Spatial Separation:** Real point clouds are never conflated with synthetic Airoli demo data.
- **Reporting:** Reports only measured point counts, bounding envelopes, and extracted geometric polygons without manufacturing synthetic ground truth.

---

## 3. Placement & Execution
Place external open-source LAS/LAZ files into:
```text
/app/data/sample_pointcloud/
```
The adapter can be invoked via Python:
```python
from app.pipelines.real_data_adapter import RealDataAdapter

adapter = RealDataAdapter(sample_dir="/app/data/sample_pointcloud")
result = adapter.run_extraction_on_sample("/app/data/sample_pointcloud/sample.laz")
print(result["extraction_result"]["extracted_height_m"])
```
