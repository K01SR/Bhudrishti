# Universal Vectorized LiDAR Point Cloud Workstation

> **Canonical System Reference:** [Master Monograph Chapter 7](../docs/00-master-system-documentation.md#7-universal-vectorized-lidar-point-cloud-workstation)  
> **Source Files:** [`backend/app/api/v1/lidar.py`](../backend/app/api/v1/lidar.py), [`frontend/src/components/lidarinspector/LiDARInspector.tsx`](../frontend/src/components/lidarinspector/LiDARInspector.tsx)  
> **Tests:** [`tests/test_api_endpoints.py:test_universal_lidar_streaming_endpoints`](../tests/test_api_endpoints.py)

---

## 1. Zero-Copy Binary Streaming Protocol

Traditional point cloud transmission uses bulky LAS/LAZ or uncompressed JSON formats. Bhu-Drishti 3D implements a **direct NumPy vectorized surface discretization and zero-copy binary streaming pipeline** serving 8-float contiguous records (32 bytes per point) via `application/octet-stream`.

### Binary Layout (Float32Array)
| Offset | Type | Field | Description |
|:---:|:---:|:---:|:---|
| 0 | float32 | `x` | Easting (meters) |
| 1 | float32 | `y` | Northing (meters) |
| 2 | float32 | `z` | Elevation above ground datum (meters) |
| 3 | float32 | `classification` | ASPRS Class (2=Ground, 3=Wall, 5=Vegetation, 6=Roof) |
| 4 | float32 | `intensity` | Laser pulse return intensity (0 - 255) |
| 5 | float32 | `r` | Red channel (0 - 255) |
| 6 | float32 | `g` | Green channel (0 - 255) |
| 7 | float32 | `b` | Blue channel (0 - 255) |

## 2. API Endpoints
* `GET /api/v1/lidar/pointcloud`: Structured JSON point cloud metadata with bounding envelopes.
* `GET /api/v1/lidar/pointcloud/binary`: Zero-overhead Float32Array streaming in sub-20ms.
