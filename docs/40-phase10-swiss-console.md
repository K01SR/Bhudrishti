# Phase 10 — Swiss console, inside the application

## What this is

The Swiss (International Typographic) UI lived only on the marketing surface.
`src/components/landing/CadastralDeepTelemetry`, `CadastralDocsHub`,
`CadastralSpatialCharts` and `CadastralWireframeInspector` each take a
`theme: 'brutalist' | 'swiss' | 'kinetic' | 'neo' | 'botanical'` prop and ship
five visual variants of the same showcase panels.

That surface is under a byte-identical protection, so it cannot be edited or
removed here. What could be done is to build the idiom properly where it is
actually used: a **System Console** at `/app/console`, in the application
shell, beside the map and the other operator tools.

## Why the data could not be moved with the design

The landing components render invented figures. From
`CadastralDeepTelemetry.tsx`:

```
{ name: 'Thane',   parcels: '2,84,591', twinsActive: '38,410',
  clashAlerts: '12 (Resolved)', concordance: '99.98%', status: 'OPERATIONAL' }
```

State-wide registry counts, twin counts, clash alerts, concordance percentages
and an `OPERATIONAL` status, for five districts, with no backing data anywhere
in the system. `CadastralDeepTelemetry` also ships a ULPIN check-digit
calculator whose result is a hardcoded `'4'`.

None of that can move into the application. So the console keeps the *style*
and replaces the *content* with what this deployment actually measures.

## The console

`frontend/src/pages/app/SwissConsolePage.tsx`, primitives in
`frontend/src/components/swiss/Swiss.tsx`. Four panels, each fed by a real
endpoint:

| Panel | Source | What it shows |
| --- | --- | --- |
| Open-data inventory | `/opendata/stats` | buildings held, regions cached, cache entries, authoritative regions, provider configuration |
| Ground-profile pipeline | `/system/benchmarks` | measured Python / Rust / C++ milliseconds and speedups |
| Precinct fabric | `/osm/summary` | **computed fields only** — see below |
| Validation | `/validation/run` | raw validation output |

Every absent value renders `--` with a reason. No figure is inferred, defaulted
or carried over from a previous panel.

## The honest part: what `/osm/summary` withholds

While wiring the fabric panel I read the handler
(`backend/app/api/v1/osm.py:700`). It mixes two kinds of value:

**Genuinely computed** from the arrays it returns — `total_roads_km` (measured
from the street geometry), `streetlights_installed` and `shade_trees_planted`
(counts of the coordinate arrays), `total_pois` (length of the amenity array).

**Hardcoded literals** presented in the same response:

- `primary_arterials_count: 2`, `collector_roads_count: 2`,
  `residential_lanes_count: 4`, `crosswalks_count: 14` — never derived.
- `parks_count`, `ward_offices`, `health_clinics`, `police_posts`,
  `ev_charging_hubs`, `power_substations`, `bus_transit_shelters` — each
  literally `1`.
- `geospatial_accuracy`: `dgps_rtk_closure_error_mm: 2.4`,
  `elevation_datum: "Survey of India GTS Benchmark"`,
  `horizontal_tolerance_m: "< 0.02m (Survey Grade)"`.

That last block is the serious one. It asserts that the mapping is certified to
a Survey of India datum at sub-2cm tolerance. Nothing in this system has been
surveyed to that tolerance, and presenting it as a measured field is a claim of
government-grade certification that does not hold.

The console therefore shows only the computed group and states on screen that
the rest exists and is unmeasured. It does not even restate the fabricated
figures, so the invented numbers do not propagate through a second surface.

`COMPUTED_FABRIC` / `COMPUTED_AMENITIES` in the page are the allowlist. If the
backend later makes one of these real, moving it out of the withheld note is a
one-line change, and the reason is written next to the line that excludes it.

This is a **backend honesty defect, not a frontend one.** It is filed for
Phase 2. The console treats the symptom; it does not fix the source, and the
endpoint still returns the fabricated block to any other caller.

## What the landing does with the same data

Nothing is imported from `src/components/landing/`. Beyond the protection, a
console that imported a marketing component would inherit a five-way theme
switch that means nothing to an operator. The style is re-expressed against the
application's own tokens (`chalk`, `canvas`, `ink`, `accent`) so the console
does not read as a foreign surface next to the map.

Two implementation notes worth keeping:

- Grid spans are a **static map** of literal class strings, not
  `md:col-span-${span}`. Tailwind scans source text for complete class names,
  so an interpolated class is absent from the generated CSS and the span
  silently does nothing.
- The withheld notes carry `data-testid="swiss-unverified-note"` so the honesty
  test can assert on the page *with the explanations removed*. Without it the
  test cannot tell a figure shown as data from a field named in a note saying
  it was withheld — which is exactly the distinction that matters.

## Evidence

`frontend/e2e/console.spec.ts` — 3 tests, green on three consecutive runs:

- Renders measured figures with no console errors.
- Withholds every literal from `/osm/summary`: no `mm` figure, no
  survey-grade or datum claim, none of the civic counts. Asserted against the
  page with the explanatory notes stripped out.
- Still shows the fabric figures it does trust.

Full suite green: 6 perf-gate + 1 picking + 3 console, 185 backend tests, docs
verification PASS, `git diff --check` clean, landing files byte-identical.

## Carried forward

The landing's invented district statistics remain on the marketing surface. Per
instruction they are left alone and recorded for Phase 11 (demo removal), which
is the phase that lifts the protection. Listed there as a known integrity
defect, not as a styling question.
