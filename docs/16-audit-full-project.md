# 16 · FULL PROJECT AUDIT

**Date:** 2026-09-26
**Scope:** live system only (`backend/`, `frontend/src`, `data/`, `tests/`, `docs/`, infra files). `old/` excluded (legacy).
**Method:** five parallel deep-dive agents (backend/auth, frontend/UX, 3D/GIS/LiDAR, pipelines/QA/data, infra/tests/docs) plus first-hand re-verification of every high-impact claim.

**Legend:** `[√ VERIFIED]` = re-confirmed personally (grep / curl / live probe / byte-count). `[agent]` = sub-agent finding, consistent across reports.

---

## 1. What we are building

Bhu-Drishti 3D — a Smart City (Airoli Sector 8, Navi Mumbai) demo platform for 3D digital cadastre:

- parcel / building lookup and analytics
- 2D map + 3D map + 3D building viewer + LiDAR + LiDAR-inspect views
- verification workflow with Ed25519 digital signatures and QR / generic-token public certificate verification
- "Ask the Map" spatial chat
- modular landing site with 6 visual themes

**Sizing:** 251 tracked files · 53,843 LOC (excl. `old/`) · 30 API route files → 113 endpoint routes · 16 existing docs · 10 test files / 46 test functions.

---

## 2. Vision vs reality

| Vision | Reality |
| --- | --- |
| Role-based cadastral workflow | 100% anonymous-capable (see Section 20) |
| Tamper-evident hash-chain audit | In-memory list mutation, no chain persisted |
| Real PostGIS parcel store | 5–6 of 30 route files touch the DB; the rest serve import-time dicts |
| Verified accuracy | `accuracy_m 0.05` asserted, never measured |
| Real 3D buildings | 21 of 22 GLBs are empty 52-byte containers |

---

## 3–19. Section-by-section findings

### Backend (REAL but thin)
FastAPI + async SQLAlchemy/Postgres + PostGIS are real. The DB path in `auth.py` (`select(User)`) is real. Most other endpoints serve module-level in-memory dicts.

### Frontend (REAL, large)
Vite + React + TS, 21 routes (`App.tsx:70-105`), maplibre / three.js, ~9,300 LOC landing with 6 themes. **Zero fetch/axios calls in the entire landing tree** `[√ grep: 0 matches]`.

### Verification engine (PARTIAL REAL)
`/qr/verify/{token}` genuinely recomputes the geometry fingerprint and re-verifies the Ed25519 signature. Everything around it (chain, persistence) is fake.

### Data pipeline (REAL, synthetic)
Deterministic generator; SHA-256 seed signature `63bbc74b32c9941f` `[agent]`; hero LAS = 28,800 points, classes `2:18870 / 5:1717 / 6:8213`, seed `271828`, EPSG:32643 with local offsets, `accuracy_m 0.05` asserted-not-measured.

### 3D viewer (MOCK data)
`data/model_assets/AST-410CDB15400D/model.glb` = 4,396 bytes (real). **21 of 22 `model.glb` files = 52 bytes (empty containers)** `[√ verified byte sizes: du -b]`.

### 2D / Satellite (MISLABELED)
`GoogleSatelliteView` loads **Esri World Imagery** — it is not Google tiles despite the name `[agent]`.

### Building analytics / 3D layers (PARTIAL)
Real data slices exist for the hero parcel only; every other precinct has no usable geometry to analyze.

### Ask the Map / Chatbot (PARTIAL / static)
Ask-the-Map is partially implemented `[agent]`; chatbot responses are static.

### QR / Certificate (PARTIAL REAL)
Public verify endpoint is real; the frontend hardcodes demo tokens and ignores HTTP errors (see Section 21).

### Demo seeder / migrations
`seed_demo.py` **generates a fully synthetic dataset, prints summaries, and never writes a single row** — no `INSERT`, no `session.add` anywhere `[√ read entire file]`. No Alembic migration tooling.

### Microservices / Queues
Celery app + `worker` container exist, **zero `.delay()` call sites** `[agent]` → the pipeline never runs in the worker.

### Postgres / caching (REAL, underused)
Exactly 6 route files touch the database directly `[√ grep]`.

### LiDAR (PARTIAL)
`lidar.py:258-283` accepts `building_code` and `ulpin`; `lidar_inspect.py` remains hero-LAS-only. Per-building synthetic clouds (`synthetic_lidar_points_by_ulpin`) exist in the generator (rng `271828 + idx*1013`, 5k–14k points, classes 2/5/6).

### Tests
Backend pytest: 13 green (run prior to the latest synthetic-generator edit; not re-run after). **Frontend/pages/stores/features: 0 tests** `[agent]`. No E2E.

### Docs
16 files; several overclaim against code — most notably `docs/07-topology-rules` still describes the old SQL 12-rule verifier while the code + tests now run a new scope-verifier unit.

---

## 20. Security — the killer section (all `[√ VERIFIED]`)

1. **`require_roles()` is dead code.** Defined at `security.py:87`; **zero call sites** `[√ rg]`. No endpoint ever enforces a role.

2. **Login ignores passwords for demo users.** `auth.py:82-99` returns a token as soon as the username exists in `DEMO_USERS` — `form_data.password` is never read. **Live probe:** `POST /api/v1/auth/login` with `username=state.admin&password=WRONGPW` → **HTTP 200 + a valid token** `[√ curl]`.

3. **Every endpoint accepts anonymous "PUBLIC" tokens.** `OAuth2PasswordBearer(... auto_error=False)` (`security.py:57`) and `get_current_user_payload` returns `role="PUBLIC"` when no token is supplied (`security.py:72-75`). Dependencies never check the role.

4. **Proof — full anonymous admin action:** `POST /api/v1/verification/cases/case-b17-001/decide {"decision":"APPROVE"}` with **no token, no login** → case transitioned `NEEDS_REVIEW → APPROVED`, Ed25519 signature generated, response `"successfully transitioned"` `[√ curl]`.

5. **Hardcoded secrets committed to the repository** `[√ read]`:
   - JWT `SECRET_KEY = bhu_drishti_3d_super_secret_jwt_key_airoli_2026_cadastre` — `config.py:15`, `.env.example:5`, `docker-compose.yml:66`.
   - **Ed25519 PRIVATE key hex** `7a4d9526786c2e36b3df516147bb0630b9101d2d3a37c92b23c2a382c40c1110` — `config.py:27` (default), `.env.example:33`.
   - Postgres password `bhudrishti_secure_spatial_2026` — `config.py:23`, `.env.example:13`.
   - MinIO `minioadmin` / `minioadmin_secure_spatial` — `config.py:26`, `.env.example:28`.

6. **CORS open-plus-credentials:** `allow_origins=["*"]` **and** `allow_credentials=True` — `main.py:21-26` `[√ read]`.

7. The frontend **never sends an `Authorization` header** anywhere `[√ grep api.ts]`.

---

## 21. Frontend flaws `[agent, consistent]`

- All 21 routes are open (no guard HOC); role checks in `AppContext` are cosmetic.
- No `ErrorBoundary`; any thrown render = white screen.
- `PublicVerifyPage` ignores `res.ok`; on error it renders a "certificate" of the error object.
- `QRVerificationModal.tsx:19` hardcodes `DEMO-QR-TOKEN-AIROLI-B17` and `CERT-3D-AIROLI-B17-2026`.
- `PropertyDetail.tsx:104` `synthesizePropertyFromParcel` invents unit/rights data with hardcoded fallbacks instead of fetching the true cadastre.
- `noUnusedLocals: false` masks dead code.

---

## 22. Data truth `[agent]`

- **FSI lies.** `precinct_buildings()` sets `fsi_target` (1.85, 1.9, …) but the dataset computes `fsi = floors / 2.5`: B-01 1.85 vs **4.8**, B-11 1.9 vs **8.0**, B-12 `fsi_target: 0.0` (unused) vs computed 1.2.
- **Hero B-17 forced PASS.** `total_built_up_area_m2 = 1800` → `calculated_fsi = 1.80` forced, while true geometry ≈ **2.55** (which would FLAG). `precinct.py:23` hardcodes `fsi_status: "PASS"`.
- `metrics.py:90-105` charts **hardcoded latencies** (45.2 / 12.8 / 284.1 / 88.4 / 310.5 / 215.3 / 24.6 / 3.1 ms) `[√ read]`. Blockchain / audit-chain / hash-chain numbers are fabricated literals in route responses.

---

## 23. Bug database

| ID | Sev | Issue | Evidence |
| --- | --- | --- | --- |
| P0-1 | P0 | Complete RBAC bypass — anonymous approval possible | curl: no-token APPROVE succeeded |
| P0-2 | P0 | Ed25519 private key + JWT secret committed in 3 files | config.py:15,27; .env.example:5,33 |
| P0-3 | P0 | CORS `*` + credentials | main.py:21 |
| P0-4 | P0 | Ed25519 signatures signed by a hardcoded "signer authority" string | auth.py signer literal |
| P1-1 | P1 | Verification ledger / cases / approvals = RAM, lost on restart | verification.py `_CASES_DB` |
| P1-2 | P1 | 21/22 buildings have no 3D geometry | byte-size verified |
| P1-3 | P1 | `GoogleSatelliteView` is not Google | agent |
| P1-4 | P1 | Demo login accepts any password | curl WRONGPW → 200 |
| P1-5 | P1 | FSI / accuracy / latency metrics fabricated | precinct.py:23; metrics.py |
| P1-6 | P1 | seed_demo never writes to DB | file read |
| P2-1 | P2 | No frontend boundaries/tests; verify ignores res.ok | agent |
| P2-2 | P2 | Landing 2.5D FSI chart uses spec values ≠ dataset floors/2.5 | code + agent |
| P2-3 | P2 | Docs stale vs new verifier | docs/07 vs tests |
| P3-1 | P3 | Celery connected, never dispatched | agent |

---

## 24. Priority fix plan (dependency-ordered phases)

- **Phase 0 — HOTFIX.** Rotate/remove hardcoded secrets; make them env-only with generated dev defaults. Fix CORS. Require passwords for demo accounts.
- **Phase 1.** Wire `require_roles` onto every state-changing route (decide, sign, mint, pool, upload, ledger) and reject anonymous writes.
- **Phase 2.** Persist cases / ledger / hash-chain in Postgres; real chain transitions.
- **Phase 3.** Frontend sends `Authorization`; guard HOC + ErrorBoundary; fix `/verify` `res.ok`; de-hardcode QR modal + PropertyDetail.
- **Phase 4.** Fix hero FSI / accuracy (measure, don't assert); reconcile `fsi_target` vs `floors/2.5`; replace hardcoded metrics.
- **Phase 5.** Real `seed_demo` (actual inserts) + migration tooling.
- **Phase 6.** Honest 3D assets and correct satellite provider naming.
- **Phase 7.** Frontend tests + E2E; wire Celery or remove it; sync README/docs.

---

## 25. Final project state

**It works, end-to-end, as a demo on synthetic data — with a decorative security layer and a real Postgres underbelly that almost nobody uses.**

The most dangerous truth is not that the data is fake. It is that **a stranger can log in as the state administrator with any password and approve a cadastral case, digitally signed.** That is the first thing to fix, before any feature work.

## What I would work on first (dependency order)

1. Kill the RBAC hole — enforce `require_roles` on all write routes, reject anonymous writes (P0-1, P1-4). ~2 h.
2. Rotate every hardcoded secret to env-only (P0-2). ~30 min.
3. Tighten CORS (P0-3). ~5 min.
4. Move the verification ledger/decisions to Postgres (P1-1) — makes signatures meaningful (P0-4). ~half day.
5. Frontend: auth header, guard HOC, ErrorBoundary, `res.ok` on `/verify` (P1-4, P2-1). ~half day.
6. Data truth: hero FSI, measured accuracy, honest metrics (P1-5). ~half day.
7. Real `seed_demo` (P1-6). ~1 h.
8. Re-sync README/docs with reality.

---

*No source code was modified during this audit (RULE 5). Re-verification commands: `rg`, `curl`, `du -b`, file reads.*