# Phase 1a - invalidation and resource leaks

Date: 2026-09-29
Baseline commit: `ce19230` (Phase 0, `docs/37-phase0-repro-report.md`)

Phase 0 measured four problems. This phase fixes the first one properly: the 3D
map rebuilt its entire scene, and its WebGL context with it, on changes that had
no business touching geometry. It also fixes the label thrash, the shadow-map
per-frame cost, the rAF leaks, and the OSM rebuilds that Phase 0 saw as extra
scene builds.

## What was wrong, and what it cost

Every number below is from `frontend/e2e/perf-gate.spec.ts` on SwiftShader, with
no GPU. They are not hardware figures. They are comparable to each other, and
comparable to the Phase 0 baseline on the same machine.

Phase 0, one area switch:

| | Phase 0 | Phase 1a |
|---|---|---|
| scene build | 532-965 ms | 47-59 ms |
| scene builds on a cold load | 2-3 | 1 |
| worst frame | 700-983 ms | 217-267 ms |
| WebGL contexts across 3 switches | 2 -> 5 | 1 |
| geometries across 3 switches | 414 -> 535, never released | returns to baseline |

### The three causes, in order of cost

**1. The renderer was recreated on every data change.** `forceContextLoss` alone
was 1109 ms of a 1233 ms stall, found with a CDP sampling profile. The leak fix
that made contexts climb correctly was itself the freeze. The fix is the one the
profiler pointed at: split the effect in two.

`PrecinctMap3D` now has a mount-only effect (deps `[]`) that owns the
`WebGLRenderer`, the scene, the camera, the render loop, the DOM label layer and
every event listener, and a content effect (deps `[validParcels, hero, buildings,
overlayModel]`) that builds meshes into a single `content` group and disposes
that group on the next data change. Nothing in the second effect can reach the
context, so a data change is a content rebuild and a full teardown happens only
on unmount.

**2. ~500 fresh materials per rebuild, each forcing a shader compile.**
`getProgramInfoLog` plus `getShaderInfoLog` was 25% of the main thread. The
colours come from small closed sets (`TYPE_COLORS`, `STATUS_COLORS`,
`HIGHWAY_COLORS`), so a handful of distinct programs suffice, but a new material
per mesh defeats the driver's program cache. Materials now come from a shared
cache keyed by the values that change them, and teardown skips them via
`SHARED_MATERIALS`. Program count is stable at 6 across switches.

**3. React re-rendered the whole 3D view on every keystroke.** The scene effect
was already immune after `overlayModel` was memoised, but `MapPage` re-rendered
`PrecinctMap3D` on each latitude keystroke and a measurement still showed six
keystrokes producing six long frames. Every prop is referentially stable across
a keystroke, so the component is now `React.memo`'d. The cost of typing is now
+16 ms over an idle baseline, from +66 ms.

### Also fixed

- **OSM urban fabric** was built inside the scene effect while its four datasets
  were dependencies of it, so each arrival tore down the whole scene. It is now
  `buildOsmFabric` in its own effect, disposing its previous contents.
  Cold-load scene builds went from 2-3 to 1.
- **Shadow map** re-rasterised every caster into a 2048px depth target every
  frame, a second full scene pass at 30-60 Hz producing an identical result.
  `autoUpdate = false` with `needsUpdate` re-asserted after each async addition.
- **Labels** read `offsetWidth`/`offsetHeight` and wrote `left`/`top` per label
  per pass, forcing layout twice per label at ~235 labels and 30 Hz. Dimensions
  are now measured once at creation and position comes from `translate3d`.
- **The render loop** kept running when the tab was hidden or the map was
  scrolled out of view, and was never cancelled on unmount. It now suspends on
  `visibilitychange` and `IntersectionObserver`, and cancels on unmount.
- **The flyover rAF** was never cancelled and could outlive the scene by
  `FLYOVER_MS`, writing to camera refs the next scene reads.

## The gate

`frontend/e2e/perf-gate.spec.ts` turns the Phase 0 numbers into thresholds so
the freeze cannot come back unnoticed. Two design points are worth stating
because they change what the numbers mean.

**Frame budgets are deltas over a same-page idle baseline, not absolutes.** An
idle 3D map on SwiftShader renders at roughly 13 fps: measured at 133-167 ms
worst frames and 418 draw calls while doing nothing at all. An absolute
long-frame budget measures the machine, not the code. Every interaction budget is
therefore "how much worse than doing nothing is this interaction", measured on
the same page in the same test. Scene-build and leak budgets stay absolute,
because those are properties of the application.

**The leak check compares the same area in the same state, twice.** An earlier
version compared geometry counts across *different* areas and reported a
121-geometry leak that was not a leak: cold-load Airoli holds 414 geometries
before its OSM refetch completes and 535 after, and Pune and Bengaluru hold
different amounts again. The gate now returns to the starting area twice and
compares those two, which differ only if something is retained.

Two further gate bugs were found and fixed while making it honest:

- `resetPerf` zeroed `sceneBuilds` and `webglContexts`. Both are cumulative
  facts about the page, not rates, so a test that resets between windows was
  comparing two unrelated numbers. They now survive a reset.
- Artifacts were written once in `afterAll` from a shared `report` object. A
  worker restart after a failure silently reset it, and the accumulated object
  meant every per-test file also carried the other five tests' numbers. Reports
  are now per-test and rebuilt per test.

The unmount test asserts the WebGL context count returns to 1, not 0: the 2D
Cadastre Atlas is MapLibre, which is itself WebGL, so the incoming view claims a
context. What must not happen is 2, the three.js context surviving its own
unmount. The counter is driven by a `webglcontextlost` listener, so this is the
browser reporting release rather than the app asserting it about itself.

## Current measurements

Cold load: 12 ms scene build, 1 build, 414 geometries, 1 context.

Area switching, against a 133 ms idle baseline in the same run:

| hop | scene build | builds | worst frame | over idle | long frames over idle | geometries | contexts |
|---|---|---|---|---|---|---|---|
| Pune Shivajinagar | 59 ms | 1 | 267 ms | +134 | 0 | 490 | 1 |
| Bengaluru MG Rd | 47 ms | 1 | 217 ms | +84 | +1 | 532 | 1 |
| Airoli S8 | 54 ms | 1 | 233 ms | +100 | +1 | 535 | 1 |

Two consecutive visits to Airoli: 535 then 535 geometries, 1 context both times.

Typing: 6 keystrokes, 1 scene build before and after, worst frame +16 ms over
idle. Layer toggles: 3 toggles, 0 rebuilds, worst frame -17 ms over idle.

## How to re-derive

```bash
cd frontend
npm ci
npm run build
VITE_PROXY_TARGET=http://localhost:8000 npx vite preview     # serves :3100
E2E_BASE_URL=http://localhost:3100 npx playwright test e2e/perf-gate.spec.ts
ls e2e/.artifacts/gate-*.json
```

Six tests, all passing. Each writes its own artifact containing only its own
measurements.

## Not done here

- **Batching and instancing.** ~500 draw calls for a scene of this size is still
  wrong, and 418 while idle is the floor the frame budgets are measured against.
  That is Phase 1b; it is what will move the absolute numbers, and it should
  re-derive the idle baseline afterwards.
- **LiDAR streaming**, Phase 1c, unchanged here.
- **The Bandra preset** and the wider five-cycle area-switch gate. The gate
  currently covers Airoli, Pune and Bengaluru.
- A Chrome performance trace. The gate reports what the app's own instrumentation
  measured; an external trace would be a useful independent check on it.
