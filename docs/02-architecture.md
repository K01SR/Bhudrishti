# Bhu-Drishti 3D — System Architecture & Technology Stack

## 1. Architectural Blueprint
```
                         ┌──────────────────────────────────────────────┐
                         │           Bhu-Drishti 3D Frontend            │
                         │    React 18/19 + TypeScript + Tailwind CSS   │
                         │     MapLibre GL (2D) + Three.js (3D)         │
                         └──────────────────────┬───────────────────────┘
                                                │ REST / JSON (OpenAPI)
                                                ▼
                         ┌──────────────────────────────────────────────┐
                         │            FastAPI Modular Core              │
                         │    RBAC Security, 3D ULPIN Engine, QA Rules, │
                         │    Lifecycle State Machine, Ask-the-Map      │
                         └───┬──────────────────┬──────────────────┬────┘
                             │                  │                  │
                PostGIS / SQL│                  │ Tasks            │ S3 API
                             ▼                  ▼                  ▼
                 ┌───────────────────┐  ┌───────────────┐  ┌───────────────┐
                 │    PostgreSQL     │  │ Redis Celery  │  │ MinIO Storage │
                 │   16 + PostGIS    │  │ Workers       │  │ (Raw, Derived,│
                 │   + 3D Topology   │  │ (AI Pipeline) │  │  Certificates)│
                 └───────────────────┘  └───────┬───────┘  └───────────────┘
                                                │
                                    ┌───────────┴───────────┐
                                    ▼                       ▼
                              PDAL / Shapely        Point Density &
                              Building Extractor    Floor Segmenter
```

---

## 2. Core Technology Stack
- **Frontend:** React 18, TypeScript, Three.js (3D Digital Twin rendering, clipping planes, raycasting), MapLibre GL JS (2D Cadastral boundary maps), Tailwind CSS, Lucide icons.
- **Backend Framework:** FastAPI (Python 3.11/3.14), Pydantic v2 (Canonical Property Data Schema validation), SQLAlchemy 2.0 (async + sync sessions), GeoAlchemy2.
- **Database:** PostgreSQL 16 with PostGIS spatial extensions (`postgis`, `postgis_topology`).
- **Asynchronous Task Queue:** Celery with Redis broker and result backend.
- **Spatial Object Storage:** MinIO (S3-compatible API) with local filesystem caching fallback.
- **Cryptography:** Ed25519 asymmetric signatures (via Python `cryptography` primitives) and SHA-256 tamper-evident hash chaining.
- **Deployment & Orchestration:** Docker Compose multi-container microservice topology with automated healthchecks.
