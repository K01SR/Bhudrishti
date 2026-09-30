# Complete REST API Specification Reference

> **Canonical System Reference:** [Master Monograph Chapter 16](../docs/00-master-system-documentation.md#16-complete-rest-api-specification-reference)  
> **OpenAPI Swagger:** `http://localhost:8000/docs`  
> **Source Files:** [`backend/app/api/v1/router.py`](../backend/app/api/v1/router.py)

---

## 1. Key Endpoints Matrix
| Method | Path | Summary | Response |
|:---:|:---|:---|:---|
| `GET` | `/api/v1/properties/hero` | Hero Building B-17 record | Property JSON |
| `GET` | `/api/v1/lidar/pointcloud/binary` | Universal LiDAR Binary Stream | `application/octet-stream` |
| `GET` | `/api/v1/exports/pdf/property-card/{ulpin}` | 4-Page Vector Property Card PDF | `application/pdf` |
| `GET` | `/api/v1/exports/latex/property-card/{ulpin}` | Compilable LaTeX Source | `application/x-latex` |
| `GET` | `/api/v1/precinct/buildings` | Precinct 13-Building Metadata | JSON Array |
| `GET` | `/api/v1/precinct/heatmap/{mode}` | FSI/Risk/Value Heatmap | Heatmap JSON |
| `GET` | `/api/v1/audit/events` | In-process audit chain | Audit Event Array |
| `GET` | `/api/v1/audit/verify-chain` | Merkle Chain Integrity Status | Verification JSON |
