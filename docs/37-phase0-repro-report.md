# Phase 0 - reproduction and profiling report

Date: 2026-09-29
Baseline commit: `6d82898`
Scope: the four reported issues on the Bhu-Drishti 3D `/app` interior.

No product code was changed in this phase. The only additions are measurement
infrastructure (`frontend/src/perf/`, `frontend/e2e/`,
`frontend/playwright.config.ts`) so that every claim below is a number someone
else can re-derive rather than an impression.

## How to re-derive this report

```bash
cd frontend
npm ci
npm run build
VITE_PROXY_TARGET=http://localhost:8000 npx vite preview     # serves :3100
E2E_BASE_URL=http://localhost:3100 npx playwright test e2e/repro.spec.ts
cat e2e/.artifacts/phase0-report.json
```

The suite runs against `vite preview` rather than `npm run dev` on purpose.
`main.tsx` mounts under `React.StrictMode`, which double-invokes effects in
development, so the 3D scene would build twice per mount and the frame timings
would describe a development-only condition.

Headless Chromium has no GPU here, so WebGL runs on SwiftShader via the
`--use-gl=angle --use-angle=swiftshader` flags in `playwright.config.ts`.
Absolute frame times are therefore pessimistic relative to hardware. The
*relative* cost of each operation, which is what the fixes target, is unaffected.

## Issue 1 - `/app/map?view=3d` freezes after loading a different area

**Reproduced. Confirmed and worse than reported.**

Cold load of the default 3D view, before any interaction:

| Metric | Value |
|---|---|
| fps | 15.5 |
| worst frame | 383 ms |
| long frames (>100 ms) | 10 |
| scene build | 343 ms |
| draw calls | 418 |
| geometries | 414 |
| WebGL contexts | 2 |

Area switches, measured independently per hop:

| Hop | scene build | area load | worst frame | long frames | geometries | contexts |
|---|---|---|---|---|---|---|
| Pune Shivajinagar | 532 ms | 61 ms | 700 ms | 14 | 490 | 3 |
| Bengaluru MG Rd | 878 ms | 66 ms | 933 ms | 22 | 532 | 4 |
| Airoli S8 | 965 ms | 62 ms | 983 ms | 26 | 535 | 5 |

Three things fall out of this table.

**The stall is scene rebuild, not the network.** The area request itself takes
61-66 ms. The scene rebuild that follows takes 532-965 ms, roughly ten times
longer, and it lands on the main thread as one synchronous block. A user
switching areas watches a frozen canvas for most of a second per switch.

**Geometries and draw calls grow monotonically and never come back down.** 414
geometries at load, 490 after Pune, 532 after Bengaluru, 535 after returning to
Airoli. Returning to the original area does not restore the original state. This
is the leak, and it is visible in the numbers rather than inferred.

**WebGL contexts accumulate one per rebuild, 2 to 5 across three switches.** The
cleanup path calls `renderer.dispose()` but never `forceContextLoss()`, so the
context is not reclaimed. Chrome starts refusing new contexts at roughly 16;
at five per area switch that ceiling is a handful of switches away, and the
failure mode is a silently blank canvas rather than an exception.

### Issue 1b - the same stall from a single keystroke

Typing six characters into the map's latitude field, with no area load at all:

| Metric | Value |
|---|---|
| long frames from 6 keystrokes | 12 |
| worst frame | 183 ms |
| per-keystroke stall | 100-183 ms, all 12 |

Every keystroke in that field costs two long frames. The cause is
`frontend/src/pages/app/MapPage.tsx:141-148`, where `overlayModel` is an object
literal built on every render. It is a dependency of the scene-construction
effect at `frontend/src/components/map3d/PrecinctMap3D.tsx:1365`, so a state
change anywhere in `MapPage` tears down and rebuilds the entire three.js scene
and its renderer. The effect has 17 dependencies; this one is the worst because
it changes identity on every single render regardless of whether anything
relevant changed.

`toasts` trigger the same path, so any `showToast` is also a full scene rebuild.

### Confirmed contributing causes

Each of these was verified by reading the code at the cited lines.

| Cause | Location |
|---|---|
| `overlayModel` literal is a scene-effect dependency | `MapPage.tsx:141-148`, `PrecinctMap3D.tsx:1365` |
| Cleanup calls `renderer.dispose()` only; no geometry/material traversal, no `forceContextLoss()` | `PrecinctMap3D.tsx:1348-1363` |
| Label projection interleaves `offsetWidth` reads with `style.left` writes for ~235 labels at 30 Hz, forcing two layouts per label per update | `PrecinctMap3D.tsx:1315-1327` |
| deck.gl layers assembled in the effect body, not `useMemo`; inline arrow callbacks passed as effect deps, so every parent render re-tessellates | `DeckGL3DOverlay.tsx:124-213`, `MapLibreCadastreMap.tsx:751-752` |
| 2048x2048 PCFSoft shadow map with `autoUpdate: true` re-rendered every frame on a static scene | `PrecinctMap3D.tsx:612-614,622` |
| ~760 independent `Mesh` objects each with own geometry and material; no instancing or merging | `PrecinctMap3D.tsx:664-1003` |
| `flyAnimRef` never cancelled in effect cleanup, so a flyover can outlive the scene and keep writing to shared camera refs | `PrecinctMap3D.tsx:1348-1363` vs `1413-1425` |
| `buildings` grows on every area switch, and `MapPage` never prunes on switch | `MapPage.tsx:67-88` |
| Up to 3 concurrent `PrecinctMap3D` instances on the Overview page | `AppHome.tsx:336,466,596,1015` |

**Correction to the expected-findings list in the original report.** Web Workers
are *not* where the win is. The measurements above show the dominant cost is
synchronous scene teardown and rebuild triggered by React state changes, plus
per-frame layout thrash in the label pass. Neither is helped by moving
triangulation to a worker. The prompt's Phase 1 ordering (worker first) was
reordered accordingly: fix invalidation, then batching, then workers only if the
gate still fails.

## Issue 2 - `/app/properties/X-OSM-5253660C` LiDAR view freezes or stays empty

**Reproduced, with a different root cause than reported. The page never reaches
the LiDAR view at all.**

The property API call succeeds:

```
GET /api/v1/parcels/X-OSM-5253660C   ->  200
```

The page renders a full property record. But there is **no LiDAR control on the
page**: the spec looked for a button matching `/lidar/i` and found none
(`hasLidarButton: false`), so no point cloud was ever requested. Load was not a
stall either: 2 long frames, worst 283 ms, which is the ordinary cost of the
Overview-grade scene rather than a LiDAR-specific freeze.

The record does render, and it renders itself as authoritative-looking, which is
its own problem. Visible on the page for this OSM-sourced building:

- `OFFICIAL` badge
- `Ed25519 Signed Record`
- `PROPOSED 3D EXTENSION: SURVEYED`
- `Mixed-source record: layers are ingested from authoritative survey feeds and AI extraction`

For a building whose geometry came from OSM way `353375955`, with no cadastral
record behind it. `OFFICIAL` and `SURVEYED` are not supported by anything in the
response. This is a data-truth problem, and it is a worse problem than the empty
LiDAR tab because it is confidently wrong rather than visibly blank.

Related, from reading the code: the `/app/lidar` route passes `DEMO_ULPIN` as a
hard-coded initial parcel (`LiDARInspectPage.tsx:7`), so the LiDAR workstation
is pinned to the demo parcel rather than to whatever property was opened.

**Correction to the expected-findings list.** "Unbounded point counts" and
"main-thread decode" are real code problems (`lidarApi.ts:76` re-concatenates the
whole buffer on every chunk, which is quadratic; `decodeBuffer` at
`lidarApi.ts:105-131` runs per-point on the main thread) but they are not what
the user hit on this URL, because no point data was ever requested.

## Issue 3 - a tile or logo saying a key is required

**NOT REPRODUCED. There is no keyed tile source in this codebase.**

Every tile request across all three map views, with status codes:

| View | Host | Requests | Status |
|---|---|---|---|
| cadastre | `basemaps.cartocdn.com` | 40 | 200 |
| cadastre | app origin (internal MVT `/api/v1/tiles/*.pbf`) | 6 | 200 |
| open_twin | `basemaps.cartocdn.com` | 40 | 200 |
| open_twin | `b.basemaps.cartocdn.com` | 14 | 200 |
| open_twin | app origin (internal MVT) | 6 | 200 |
| satellite | `basemaps.cartocdn.com` | 40 | 200 |
| satellite | `b.basemaps.cartocdn.com` | 14 | 200 |
| satellite | app origin (internal MVT) | 6 | 200 |

Zero requests to `tile.openstreetmap.org`, Stadia, Thunderforest, MapTiler,
Mapbox, or any other keyed provider. Zero non-200 responses. Zero placeholder
images: the spec flags any successful image under 4 KB as a likely placeholder
tile and found **0 of 134**. The satellite view's ESRI World Imagery endpoint is
the public keyless one (`EsriSatelliteView.tsx:22-24` says so in a comment).
No text matching `/api key|access blocked|requires? (an )?(api )?key|token
required|upgrade to|unauthorized/` appears anywhere in the rendered DOM. No
console errors on any view.

**The grep in the original report is a trap.** The only occurrence of
`tile.openstreetmap.org` in the entire tree is a *comment* at
`frontend/src/components/map2d/MapLibreCadastreMap.tsx:326` explaining that the
project deliberately avoids that host. Grepping for it and treating the hit as
the cause would point the investigation at a decision to do the right thing.

Most likely explanations for what was actually seen, none of them a keyed tile:
the ESRI attribution line, which embeds the project name and is easy to
misread at small size (`EsriSatelliteView.tsx:53`); a browser extension
overlaying the page; or the dead `VITE_GOOGLE_MAPS_API_KEY` entry in
`frontend/.env.example:1-3`, which no source file reads and which may have
prompted a key to be added somewhere outside the repo.

Phase 6 of the original plan therefore has no "remove the key-required logo"
work item. It reduces to: add a basemap switcher, add offline caching, delete
the dead Google Maps key from `.env.example`, and keep attribution visible.

## Issue 4 - `/app/properties/Y0B6YWPJVLTYGR` returns 404

**Reproduced, and the 404 is correct behaviour. The bug is the presentation.**

```
GET /api/v1/parcels/Y0B6YWPJVLTYGR  ->  404
{"detail": {
  "error": "no dataset ingested for this identifier",
  "explanation": "No cadastral record exists for this identifier. Building
                  geometry is available for any area via POST /parcels/ingest-area
                  or GET /opendata/area, which resolve to published footprint data
                  (Microsoft GlobalML, OpenStreetMap) with real ground elevation.",
  "not_available": [
    "parcel boundary from a land-record source (no open bulk API)",
    "floor ownership (no public dataset exists at this granularity)",
    "FSI or any compliance verdict (requires an authoritative permitted-FAR rule
     and surveyed inputs; neither is present)"
  ]
}}
```

The backend is right, and the response is exemplary: it says what is missing,
why it is missing, and what *is* available instead. The three `not_available`
reasons are accurate.

**The identifier is not in the codebase.** `Y0B6YWPJVLTYGR` occurs exactly once
in the repository, in
`data/purge_backups/national_parcels_before_purge_20260927T201958Z.json:295117`
- a pre-purge backup of the synthetic `national_parcels` table. It is not
generated by any running code path. So the original report's hypothesis of "a
generated ULPIN that was never persisted" is **rejected**: this is a purged
synthetic row, most likely linked from a stale tab, a bookmark, or a
pre-purge screenshot.

**The real user-visible bug is confirmed.** The page renders the raw JSON
payload as the page body:

```
Parcel unavailable

{"error":"no dataset ingested for this identifier","ulpin":"Y0B6YWPJVLTYGR",
 "explanation":"No cadastral record exists for this identifier. ...,
 "not_available":["parcel boundary from a land-record source (no open bulk API)", ...]}
```

Cause: `services/api.ts:44` stringifies a structured `detail` object instead of
extracting a message, and `PropertyDetail.tsx` passes it straight to
`ErrorState`. So the 404 branch leaks an internal JSON shape into the UI. This
is exactly what the original report asked for in Phase 2, and it is real.

**Two related real defects found alongside it, both of which can produce this
class of dead link:**

1. `frontend/src/components/map2d/CadastrePropertyInspector.tsx:271` renders a
   "Full Ledger" button that is **not** gated on a real parent ULPIN. Clicking it
   on an OSM-sourced building navigates to `/app/properties/OSM-{way_id}`, a
   record that cannot exist. The sibling path in
   `openstudio/RightInspectorPanel.tsx:75-77,364` gates correctly on
   `parentUlpin`; this one does not.
2. `frontend/src/components/map2d/MapLibreCadastreMap.tsx:155` classifies
   `source` as `OFFICIAL_CADASTRE` for any 14-character ULPIN. That length test
   cannot distinguish a real state-issued ULPIN from the ingest IDs minted at
   `backend/app/api/v1/parcels.py:576-585` (`X-{provider}-{sha1[:10]}`). Any
   non-state 14-char identifier is therefore labelled official.

## Measurement infrastructure added

`frontend/src/perf/perf.ts` - framework-free metrics store. Frame timing with
long-frame logging above a 100 ms threshold, three.js renderer counters, layer
and scene build times, area load time, JS heap, and a live WebGL context count.
Reports can be tagged so a stall is attributable to a named action, which is how
the 1b measurement above distinguishes "6 keystrokes" from "3 area switches".

`frontend/src/perf/PerfOverlay.tsx` - a `?perf=1`-gated HUD. Deliberately
avoids box-shadow, backdrop-filter and per-frame animation so the instrument does
not perturb what it reports.

`frontend/playwright.config.ts` - the repo had no browser test infrastructure of
any kind. `workers: 1` and `fullyParallel: false` because the stall gate needs
the machine to itself; parallel workers would contend for the single SwiftShader
context and corrupt the timings.

`frontend/e2e/repro.spec.ts` - the four reproductions above. It asserts only that
evidence was collected, never that a bug is still present, so it stays green once
Phase 1 fixes the freezes. Phase 1 replaces the recorded numbers with thresholds.

`window.__PERF__` is the test surface, so the Phase 1 gate asserts on counters
rather than scraping overlay text, and keeps working if the HUD layout changes.

## Corrections to the original brief

Four premises did not survive contact with the code. Recorded here so the
remaining phases are not planned against them.

| Brief said | Reality |
|---|---|
| A keyed tile shows a "key required" logo | No keyed tile source exists. 134 tile requests, all 200, all keyless. The `tile.openstreetmap.org` hit is a comment about avoiding it. |
| `Y0B6YWPJVLTYGR` comes from a generated ULPIN never persisted | It exists in one pre-purge backup file, in no code. The real dead-link bugs are an ungated "Full Ledger" button and a 14-char-length `OFFICIAL_CADASTRE` test. |
| Fix the freeze with Web Workers | The stall is synchronous scene rebuild from React state changes, plus per-frame layout thrash. Workers are Phase 1c, not 1a. |
| Phase 10 grep gate `12345678901234` must return nothing | The protected landing contains 5 occurrences. The gate must exempt the landing, or the two rules contradict. |

Two findings not in the brief at all:

- `lidar_inspect.py:75-172` fabricates the violation the UI reports. A 900-point
  band at z=18.0-21.5 with `intensity=245, return_number=2` is injected with
  `np.random.default_rng(271828)` inside a bare `except Exception: pass`. The
  frontend keys `epoch2_delta` on exactly `rn===2 || intensity>=240`
  (`pointCloudEngine.ts:559,573`) and prints "unauthorized 6th floor" and
  "exceeding FSI (2.10 > 2.00)" from string literals
  (`LiDARInspector.tsx:903-911`). This is scheduled as Phase 2, before any
  honest LiDAR tiering, because a MEASURED/MODELLED badge on top of fabricated
  points would make it look more authoritative than it is.

  > **RESOLVED — pulled forward from Phase 2 to Phase 0.** The generator, the
  > whole `except Exception: pass` block, and the `rn===2 || intensity>=240`
  > predicate are gone. Reading the LAS header directly confirms what the file
  > actually holds: 28,800 points (matching `metadata.json` exactly), bounds
  > Z[-3.49, 18.06], classes 2:18870 / 5:1717 / 6:8213, and **every one of the
  > 28,800 records is return_number 1** — there is no second return anywhere.
  > Two further consequences of removing the injection:
  >
  > 1. The fabricated band sat at 18.0-21.5 m, entirely above the real cloud
  >    top of 18.06 m, and the dataset's own ground truth stops at L04/18.0 m.
  >    There was never a 6th floor in evidence, and nothing to exceed.
  > 2. With the injection gone, the old `intensity>=240` branch would have begun
  >    firing on **237 real points** whose normalised intensity happened to land
  >    near the top of the range — so the fix had to remove the predicate, not
  >    just the fake points.
  >
  > `return_number` is an ASPRS return ordinal (a second bounce within one
  > scan), never an epoch marker, so it could not have supported a delta even
  > with genuine multi-return data. `/scene` now reports
  > `multi_epoch: false, epochs_available: 1`, the delta control is disabled and
  > says why, and the alert banner is deleted. Regression coverage in
  > `tests/test_honesty_regressions.py` (7 mutations verified to fail).
- The OSM property page shows `OFFICIAL` and `SURVEYED` for a building with no
  cadastral record. Recorded under Issue 2.

## Baseline for the Phase 1 gate

Recorded on SwiftShader software rendering, so treat as a pessimistic floor.

| Metric | Baseline | Target |
|---|---|---|
| Long frames on area switch | 14-26 | 0 |
| Worst frame on area switch | 700-983 ms | < 100 ms |
| Scene build | 532-965 ms | < 100 ms |
| Geometries after load, 1 hop, 2 hops, 3 hops | 414 / 490 / 532 / 535 | flat |
| WebGL contexts after 3 switches | 5 | 1-2 |
| Long frames per 6 keystrokes | 12 | 0 |
| Heap after 3 switches | 10.0 MB | no growth |
