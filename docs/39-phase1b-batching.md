# Phase 1b — geometry batching

## What this phase was for

Phase 1a fixed *when* the scene is rebuilt. It did not reduce the size of what
gets rebuilt. Phase 1b reduces the per-frame object count, which is the other
half of the cost that Phase 0 measured.

## Finding: the draw calls were not where the time was going

A census of the live scene (`renderer.info`, plus a temporary traversal of the
scene graph) found the OSM group was 408 of 418 draw calls:

| Group | Objects | Draw calls | Materials |
| --- | --- | --- | --- |
| `OSM_Urban_Fabric` | 398 | 408 | 114 |
| `Parcel_Content` | 250 | 56 | 25 |
| `Subsurface_Utilities` | 9 | 9 | 6 |

The 114 OSM materials were not 114 distinct looks. They were one shared material
per curb, sidewalk, crossing stripe, pole, lantern and tree, because
`buildOsmFabric` called `curbMat.clone()`, `swMat.clone()` and `crossMat.clone()`
once per object, bypassing the shared pool added in Phase 1a.

The colours themselves come from a small closed set (`HIGHWAY_COLORS`, 8
deterministic canopy hues, one pole material), so the objects were visually
interchangeable. Only two things were not: the 8 road surfaces and 8 amenity
fills carry `userData` used by raycasting, so they must stay addressable
individually.

## The change

`GeometryBatcher` in `frontend/src/components/map3d/PrecinctMap3D.tsx`
collects each decoration object, bakes its world transform into its vertices,
and merges the geometries by material into one mesh per material. The 16
pickable meshes are added directly and are not batched.

Merging requires identical attribute sets, so `add()` drops any geometry lacking
`normal`/`uv` rather than risking a corrupt merged buffer. Line geometry
(medians) batches separately and becomes `LineSegments`.

## Results

| Measurement | Before | After |
| --- | --- | --- |
| Cold-load geometries | 414 | 95 |
| Cold-load draw calls | 418 | 99 |
| Pune / Bengaluru / Airoli geometries | 490 / 532 / 535 | 171 / 213 / 216 |
| Pune / Bengaluru / Airoli draw calls | ~476 | 157 / 202 / 198 |
| Scene build (Pune / Bengaluru / Airoli) | 59 / 47 / 54 ms | 58 / 46 / 48 ms |
| Idle fps (3× 6 s) | 14.0 / 14.0 / 14.2 | 13.8 / 15.5 / 13.8 |

## The honest part: fps did not move

Draw calls fell roughly 4× and frame time did not change. This is expected on
the gate's renderer and is worth stating plainly rather than reporting the
draw-call drop as a speedup:

- The gate runs on SwiftShader, a CPU rasteriser. Its cost is dominated by
  pixel fill, not by the number of submitted draw calls, so cutting draw calls
  by 4× has little to remove.
- Scene build time is unchanged (58 vs 59 ms) because the same geometry is
  still being transformed; it is now merged rather than individually constructed.

So what was actually bought is a smaller scene: 3× fewer geometries to hold in
GPU memory and to traverse per frame, and ~3× fewer draw calls to submit. That
is a real saving on a hardware GPU, where draw submission is CPU-side work
against a real driver, and it makes the render loop's per-frame bookkeeping
proportional to the number of materials rather than the number of street
objects. It is **not** a measured frame-time improvement, and no such claim is
made. The fps numbers above are reported to show that the change did not
*regress* frame time on the gate renderer.

The gate therefore asserts a **draw-call ceiling** (`maxDrawCalls: 200`) rather
than a frame-time improvement. It is set above the measured 87–99 and far below
the pre-batching 418, so a later change that quietly re-splits the batch fails
the build, without being brittle to the ordinary variation in how many buildings
are in view.

## Leak check across switches

Batching is only a win if it holds across rebuilds, so the like-for-like revisit
check now records draw calls too:

- Airoli revisit: geometries `216 → 216`, draw calls `198 → 198`, contexts `1 → 1`.
- One scene build per switch; no per-switch growth.

## Gate fix found along the way

Four of the six tests took their "before" baseline after `settle()`, which only
advances frames and does not prove the scene exists. Under load the first build
landed inside the measurement window instead of before it, so a delta that was
really "the baseline was taken on an empty scene" was reported as a rebuild
caused by the interaction. All such tests now use `waitForScene()`, which waits
for GPU geometry — the same `geometries > 0` signal the leak assertions use.

Separately, an A/B measurement was invalidated early on: the preview server
serves `dist/`, so stashing the source without rebuilding loaded the same
bundle on both sides and reported "no change". Each side is now rebuilt before
measurement. The numbers above come from rebuilt bundles on both sides.

## Evidence

- `frontend/e2e/perf-gate.spec.ts` (6 tests, green on two consecutive runs)
- `frontend/e2e/.artifacts/gate-*.json` (ignored; per-test measurements)
- `docs/37-phase0-repro-report.md`, `docs/38-phase1a-invalidation-and-leaks.md`
