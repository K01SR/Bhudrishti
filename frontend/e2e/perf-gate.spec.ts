import { expect, test, type Page } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
// Pulls in the `window.__PERF__` global declaration.
import type { PerfMetrics } from '../src/perf/perf';

/**
 * Phase 1 performance gate.
 *
 * Phase 0 measured the problem and only recorded numbers. This file turns those
 * numbers into thresholds, so the same freeze cannot come back unnoticed.
 *
 * Phase 0 baseline, from `docs/37-phase0-repro-report.md`:
 *   area scene build    532-965 ms  -> < 200 ms
 *   worst frame         700-983 ms  -> see note below
 *   long frames (>100)  14-26       -> see note below
 *   geometries          414 -> 535  -> must return to baseline
 *   WebGL contexts      2 -> 5      -> must not grow past 2
 *
 * On the worst-frame and long-frame limits: this gate runs on SwiftShader, a
 * software rasteriser, where the scene renders at roughly 13 fps with nothing
 * happening at all. A measurement here confirmed an idle 3D map at 418 draw
 * calls producing 150 ms frames and 2 long frames in 5 s. An absolute long-frame
 * budget therefore measures the machine, not the code. Every interaction budget
 * here is a delta against an idle baseline measured in the same test on the same
 * page, which is the only comparison that survives a change of hardware.
 *
 * The scene-build and leak limits stay absolute, because those are properties
 * of the application: how long the main thread is blocked constructing meshes,
 * and whether GPU resources are released.
 */

type Snapshot = PerfMetrics;

const ARTIFACT_DIR = join(import.meta.dirname, '.artifacts');

const LIMIT = {
  /** Area switch must not block the main thread building meshes. Absolute. */
  areaSceneBuildMs: 200,
  /** Scene build for the initial load, first paint included. Absolute. */
  coldSceneBuildMs: 400,
  /**
   * Interaction budgets, as deltas over an idle baseline measured in the same
   * test. The area switch is allowed to be this much worse than doing nothing.
   * Phase 0's 700-983 ms frames were a 550-830 ms regression over idle; the fix
   * brings the same measurement to a 130-200 ms one.
   */
  areaSwitchExtraFrameMs: 250,
  /** Long frames the interaction may add on top of the idle rate. */
  areaSwitchExtraLongFrames: 4,
  /** Typing or toggling a layer must cost about what doing nothing costs. */
  idleInteractionExtraFrameMs: 60,
  idleInteractionExtraLongFrames: 2,
  /** Scene must not grow across switches. */
  maxGeometryGrowth: 0,
  /** WebGL contexts are not returned to the browser, so they must not accumulate. */
  maxContexts: 2,
  /**
   * Ceiling on draw calls submitted per frame.
   *
   * This is a CPU-side budget, not a frame-time one. Batching cut the scene
   * from 418 to 87 draw calls and moved measured fps by nothing (13.8-15.5 vs
   * 14.0-14.8 on SwiftShader, which rasterises on the CPU and is fill-bound,
   * not draw-call-bound). The win is real work removed from the render loop and
   * per-object bookkeeping, and it should not regress: the count is asserted so
   * a later change that quietly re-splits the batch fails the gate.
   *
   * Instancing then took it further, 99 -> 66 draws and 95 -> 61 geometries, by
   * collapsing the precinct buildings and every persisted structure onto one
   * unit box each. Both numbers are asserted together because they fail for
   * different reasons: draw calls catch units split back into separate meshes,
   * geometries catch those meshes also re-allocating their own BoxGeometry.
   *
   * Headroom over the measured 66/61 absorbs ordinary variation in how many
   * structures and OSM features are visible, while staying far below the
   * pre-instancing 99/95 and the pre-batching 418.
   */
  maxDrawCalls: 120,
  maxGeometries: 120,
} as const;

let report: Record<string, unknown> = newReport();

/**
 * Flushed after every test into a file named for that test. A single shared file
 * written in afterAll was not enough: a worker restart following a failure
 * silently reset the in-memory report, and the artifact was left holding only
 * the limits, which is precisely when a regression would go unnoticed.
 */
let currentTest = 'unnamed';

function newReport() {
  // Rebuilt per test. A single shared object meant every artifact file also
  // carried the previous tests' numbers, so a file named for one test claimed
  // measurements from five others.
  return {
    limits: LIMIT,
    notes:
      'Phase 0 baseline: docs/37-phase0-repro-report.md. Runs on SwiftShader, so frame budgets are deltas over a same-page idle baseline; build and leak budgets are absolute.',
  };
}

function flush() {
  mkdirSync(ARTIFACT_DIR, { recursive: true });
  const slug = currentTest.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase().slice(0, 80);
  writeFileSync(join(ARTIFACT_DIR, `${slug}.json`), JSON.stringify({ test: currentTest, ...report }, null, 2));
}

async function snapshot(page: Page): Promise<Snapshot> {
  return page.evaluate(() => {
    const p = window.__PERF__;
    if (!p) throw new Error('perf probe missing: load the page with ?perf=1');
    return { ...p.metrics };
  });
}

async function reset(page: Page, label = '') {
  await page.evaluate((l: string) => {
    window.__PERF__?.reset();
    window.__PERF__?.label(l);
  }, label);
}

/**
 * Wait for the scene to actually exist. settle() alone is not enough: it counts
 * animation frames, and on a cold Vite load the first 30 frames can elapse
 * before the four data fetches resolve, which produced a snapshot with zero
 * geometries and a spurious failure.
 */
async function waitForScene(page: Page) {
  await settle(page, 10);
  await page.waitForFunction(() => (window.__PERF__?.metrics.geometries ?? 0) > 0, null, { timeout: 30_000 });
  await settle(page, 20);
}

/**
 * Switch to an area and wait for the load to actually land.
 *
 * A fixed sleep is wrong here, and measurably so. Every hop is a live OpenStreetMap
 * pull behind a third-party rate limiter, and those take anywhere from 60 ms
 * (already cached) to 20 s (cold). Sleeping 6 s and snapshotting regardless
 * reported `areaLoadMs: 0` and `sceneBuilds: 0` for hops that were simply still
 * in flight, and the gate then failed with "Mumbai Fort scene builds: expected
 * 1, received 0" - a red that means the sleep was too short, not that anything
 * regressed.
 *
 * So the hop waits for the load, then settles separately. The split matters: the
 * wait bounds how long the assertion may take, and the settle is the fixed
 * window the frame and leak numbers are measured over. Measuring frames across
 * the wait instead would charge the render loop for the network wait, which is
 * the fetch's cost and not the scene's.
 */
async function switchAreaAndWait(page: Page, name: string, timeout = 90_000) {
  await page.getByRole('button', { name, exact: true }).click();
  await page.waitForFunction(() => (window.__PERF__?.metrics.areaLoadMs ?? 0) > 0, null, { timeout });
  await settle(page, 20);
}

/** Wait for frames to advance, which is the only reliable "scene is up" signal. */
async function settle(page: Page, frames = 20) {
  await page.waitForTimeout(300);
  await page.evaluate(
    (n) =>
      new Promise<void>((resolve) => {
        let i = 0;
        const tick = () => (++i >= n ? resolve() : requestAnimationFrame(tick));
        requestAnimationFrame(tick);
      }),
    frames,
  );
}

/**
 * Wait for a baseline to be taken from a scene that actually exists.
 *
 * `settle` only advances frames; it does not prove the scene has been built.
 * Four of these tests captured their "before" snapshot straight after it, and
 * under load the first build landed inside the measurement window instead of
 * before it, so a delta that was really "the scene was empty" was reported as a
 * rebuild caused by the interaction. Every test that takes a baseline now waits
 * for GPU geometry, which is the same signal `geometries > 0` exposes.
 */

async function openAreaMenu(page: Page) {
  const toggle = page
    .locator('button')
    .filter({ hasText: /Anywhere:|Airoli Sector-8 precinct/i })
    .first();
  await toggle.waitFor({ state: 'visible', timeout: 30_000 });
  await toggle.click();
  await page.getByRole('button', { name: 'Airoli S8', exact: true }).waitFor({ state: 'visible' });
}

/**
 * Measures what the map costs when nothing is happening, on this page, right
 * now. Every interaction budget is expressed relative to this.
 */
async function idleBaseline(page: Page, ms = 4000) {
  await reset(page, 'idle-baseline');
  await page.waitForTimeout(ms);
  const s = await snapshot(page);
  return {
    ms,
    maxFrameMs: Math.round(s.maxFrameMs),
    longFrames: s.longFrames,
    frames: s.frames,
    drawCalls: s.drawCalls,
    /** Long frames per second of wall clock, so windows of different length compare. */
    longFramesPerSecond: (s.longFrames / ms) * 1000,
  };
}

const consoleErrors: string[] = [];

test.beforeEach(async ({ page }, testInfo) => {
  currentTest = testInfo.title;
  report = newReport();
  consoleErrors.length = 0;
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text());
  });
  page.on('pageerror', (e) => consoleErrors.push(`pageerror: ${e.message}`));
});

// Flushed per test, not only in afterAll: a worker restart after a failure would
// otherwise discard every measurement and leave a report with only the limits
// in it, which is exactly the situation that hides a regression.
test.afterEach(() => flush());

// ---------------------------------------------------------------------------
// Cold load
// ---------------------------------------------------------------------------
test('gate: cold load builds the scene once and stays interactive', async ({ page }) => {
  await page.goto('/app/map?view=3d&perf=1');
  await waitForScene(page);

  const s = await snapshot(page);
  const idle = await idleBaseline(page, 3000);
  report.coldLoad = {
    sceneBuildMs: Math.round(s.sceneBuildMs),
    sceneBuilds: s.sceneBuilds,
    idleBaseline: idle,
    geometries: s.geometries,
    webglContexts: s.webglContexts,
  };

  expect(s.sceneBuildMs, 'cold scene build').toBeLessThan(LIMIT.coldSceneBuildMs);
  // Four OSM datasets arrive from four fetches. Before they were dependencies of
  // the scene effect, each arrival tore down and rebuilt the whole scene, which
  // showed as 2-3 builds on a cold load. One build is the contract.
  expect(s.sceneBuilds, 'scene builds on cold load').toBe(1);
  // Measured on a rebuilt bundle. An earlier A/B here compared the batched
  // source against a stale dist/ and reported no change because both runs
  // loaded the same JS; the honest comparison needs a rebuild per side.
  expect(s.drawCalls, 'draw calls per frame').toBeLessThanOrEqual(LIMIT.maxDrawCalls);
  // Paired with the count above: instances share one BoxGeometry, so a change
  // that re-splits them shows up here even if the draw call count held.
  expect(s.geometries, 'GPU geometries held by the scene').toBeLessThanOrEqual(LIMIT.maxGeometries);
  // The canvas must exist and be sized, otherwise every later number is void.
  await expect(page.locator('canvas').first()).toBeVisible();
});

// ---------------------------------------------------------------------------
// Area switching: the reported freeze
// ---------------------------------------------------------------------------
test('gate: switching areas stays under budget and leaks nothing', async ({ page }) => {
  await page.goto('/app/map?view=3d&perf=1');
  await waitForScene(page);

  // The leak baseline is taken only after the four OSM datasets have landed.
  // Before they arrive the scene holds parcel geometry alone (414); with the
  // urban fabric it holds 490. Comparing switches against the 414 figure
  // measures the OSM data arriving, not a leak, so a false +121 was reported
  // here until the baseline moved after settle.
  await openAreaMenu(page);
  const idle = await idleBaseline(page, 6000);
  const baseline = await snapshot(page);
  report.areaSwitchIdleBaseline = idle;
  report.areaSwitchBaseline = {
    sceneBuildMs: Math.round(baseline.sceneBuildMs),
    geometries: baseline.geometries,
    webglContexts: baseline.webglContexts,
  };

  // Airoli -> Pune -> Bengaluru -> Airoli, returning to the start so the
  // measurement covers deallocation as well as allocation.
  const hops = ['Pune Shivajinagar', 'Bengaluru MG Rd', 'Airoli S8'];
  const perHop: Array<Record<string, unknown>> = [];

  for (const hop of hops) {
    const window = 6000;
    await reset(page, `gate-area ${hop}`);
    // sceneBuilds is cumulative on purpose (a page-level fact, not a rate), so
    // the per-hop count is a delta against the count at the start of the window.
    const beforeHop = (await snapshot(page)).sceneBuilds;
    await page.getByRole('button', { name: hop, exact: true }).click();
    await page.waitForTimeout(window);
    const s = await snapshot(page);
    perHop.push({
      hop,
      sceneBuildMs: Math.round(s.sceneBuildMs),
      sceneBuilds: (s.sceneBuilds ?? 0) - beforeHop,
      areaLoadMs: Math.round(s.areaLoadMs),
      maxFrameMs: Math.round(s.maxFrameMs),
      maxFrameMsOverIdle: Math.round(s.maxFrameMs) - idle.maxFrameMs,
      longFrames: s.longFrames,
      longFramesOverIdle: Math.round(s.longFrames * 1000 / window - idle.longFramesPerSecond),
      geometries: s.geometries,
      drawCalls: s.drawCalls,
      webglContexts: s.webglContexts,
    });
  }

  // Leak check: return to the starting area a second time and compare like with
  // like. Different areas hold genuinely different amounts of OSM geometry, and
  // the first visit to an area can be measured before its OSM refetch has
  // finished, so comparing counts across different areas measures the data, not
  // a leak. Two visits to the same area in the same state differ only if
  // something was retained.
  await page.getByRole('button', { name: hops[hops.length - 1], exact: true }).click();
  await page.waitForTimeout(6000);
  const revisit = await snapshot(page);
  await reset(page, 'gate-area revisit');
  await page.getByRole('button', { name: hops[hops.length - 1], exact: true }).click();
  await page.waitForTimeout(6000);
  const secondRevisit = await snapshot(page);

  const after = secondRevisit;
  report.areaSwitching = {
    perHop,
    leakCheck: {
      note: 'same area, same state, two consecutive visits; differs only if something is retained',
      geometriesFirstRevisit: revisit.geometries,
      geometriesSecondRevisit: secondRevisit.geometries,
      webglContextsFirstRevisit: revisit.webglContexts,
      webglContextsSecondRevisit: secondRevisit.webglContexts,
      // Batching is only a win if it holds across switches, not just on the
      // first build. A batch rebuilt per switch would show an identical first
      // visit and a quietly climbing second one.
      drawCallsFirstRevisit: revisit.drawCalls,
      drawCallsSecondRevisit: secondRevisit.drawCalls,
    },
  };

  await page.screenshot({ path: join(ARTIFACT_DIR, 'gate-1-area-after-3-switches.png') });

  for (const h of perHop) {
    expect(h.sceneBuildMs as number, `${h.hop} scene build`).toBeLessThan(LIMIT.areaSceneBuildMs);
    // One switch, one rebuild. Two meant the OSM datasets landing separately
    // were each invalidating the scene.
    expect(h.sceneBuilds as number, `${h.hop} scene builds`).toBe(1);
    expect(
      h.maxFrameMsOverIdle as number,
      `${h.hop} worst frame over the ${idle.maxFrameMs} ms idle baseline`
    ).toBeLessThan(LIMIT.areaSwitchExtraFrameMs);
    expect(h.longFramesOverIdle as number, `${h.hop} long frames over the idle rate`).toBeLessThan(
      LIMIT.areaSwitchExtraLongFrames
    );
  }

  // Leak checks on the like-for-like revisit.
  expect(
    (after.geometries ?? 0) - (revisit.geometries ?? 0),
    'geometry growth between two consecutive visits to the same area'
  ).toBeLessThanOrEqual(LIMIT.maxGeometryGrowth);
  expect(after.webglContexts ?? 0, 'live WebGL contexts').toBeLessThanOrEqual(LIMIT.maxContexts);
  expect(revisit.drawCalls ?? 0, 'draw calls on revisit').toBeLessThanOrEqual(LIMIT.maxDrawCalls);
  expect(after.drawCalls ?? 0, 'draw calls on second revisit').toBeLessThanOrEqual(LIMIT.maxDrawCalls);
});

// ---------------------------------------------------------------------------
// Five consecutive switches
// ---------------------------------------------------------------------------
/**
 * Five switches in a row, rather than three.
 *
 * The three-switch test above returns to the start, so it covers two
 * allocations of every area it visits. A defect that only shows up once a scene
 * has been torn down and rebuilt several times - a listener that outlives its
 * scene, a geometry cache keyed on something that changes per visit, a material
 * that is cloned rather than shared - is invisible at three and obvious at five,
 * because the fifth visit is the first one that has been reached through a
 * longer chain of rebuilds.
 *
 * Bandra West is in the cycle and visited twice. It is the one area whose
 * geometry is entirely live OSM with nothing synthetic behind it, so it is the
 * clearest signal for whether retained state is per-scene or per-process: a
 * process-level retention shows up as a difference between its first and second
 * visit that the synthetic areas cannot produce, because those are refetched
 * from the same fixture.
 */
test('gate: five consecutive area switches neither leak nor exceed budget', async ({ page }) => {
  await page.goto('/app/map?view=3d&perf=1');
  await waitForScene(page);

  await openAreaMenu(page);
  const idle = await idleBaseline(page, 6000);
  const start = await snapshot(page);
  report.fiveCycleIdleBaseline = idle;
  report.fiveCycleStart = {
    area: 'Airoli S8',
    geometries: start.geometries,
    drawCalls: start.drawCalls,
    webglContexts: start.webglContexts,
  };

  // Starts on Airoli, so four switches are needed to touch four new areas and
  // return. Bandra West is deliberately adjacent in the cycle to Airoli: two
  // different real localities, so the leak comparison is not same-area.
  const hops = ['Bandra West', 'Delhi CP', 'Mumbai Fort', 'Bengaluru MG Rd', 'Airoli S8'];
  const perHop: Array<Record<string, unknown>> = [];

  for (const hop of hops) {
    const window = 6000;
    await reset(page, `five-cycle ${hop}`);
    const beforeHop = (await snapshot(page)).sceneBuilds;
    await switchAreaAndWait(page, hop);

    // The build cost has to be read here, before the counters are reset again
    // for the frame window below: reset() zeroes sceneBuilds, so a count taken
    // afterwards is 0 no matter how many builds actually happened.
    const loaded = await snapshot(page);
    const sceneBuilds = (loaded.sceneBuilds ?? 0) - beforeHop;
    const sceneBuildMs = Math.round(loaded.sceneBuildMs);

    // The frame and leak numbers are read over a window that starts once the
    // load has landed, so a slow pull does not read as a slow frame.
    await reset(page, `five-cycle ${hop} settled`);
    await page.waitForTimeout(window);
    const s = await snapshot(page);
    perHop.push({
      hop,
      sceneBuildMs,
      sceneBuilds,
      maxFrameMsOverIdle: Math.round(s.maxFrameMs) - idle.maxFrameMs,
      longFramesOverIdle: Math.round(s.longFrames * 1000 / window - idle.longFramesPerSecond),
      geometries: s.geometries,
      drawCalls: s.drawCalls,
      webglContexts: s.webglContexts,
    });
  }

  report.fiveCycle = { perHop };

  for (const h of perHop) {
    expect(h.sceneBuildMs as number, `${h.hop} scene build`).toBeLessThan(LIMIT.areaSceneBuildMs);
    // One switch, one rebuild. More would mean the OSM datasets landing
    // separately are each invalidating the scene.
    expect(h.sceneBuilds as number, `${h.hop} scene builds across five switches`).toBe(1);
    expect(
      h.maxFrameMsOverIdle as number,
      `${h.hop} worst frame over the ${idle.maxFrameMs} ms idle baseline`
    ).toBeLessThan(LIMIT.areaSwitchExtraFrameMs);
    expect(h.longFramesOverIdle as number, `${h.hop} long frames over the idle rate`).toBeLessThan(
      LIMIT.areaSwitchExtraLongFrames
    );
    expect(h.drawCalls ?? 0, `${h.hop} draw calls`).toBeLessThanOrEqual(LIMIT.maxDrawCalls);
    expect(h.geometries ?? 0, `${h.hop} geometries`).toBeLessThanOrEqual(LIMIT.maxGeometries);
    expect(h.webglContexts ?? 0, `${h.hop} live WebGL contexts`).toBeLessThanOrEqual(LIMIT.maxContexts);
  }

  // Back on Airoli after four other areas, and the scene is no larger than when
  // it was first loaded. This is the leak assertion that the extra cycles exist
  // to make meaningful: a per-visit retention would leave the last Airoli
  // bigger than the first.
  expect(
    (perHop[perHop.length - 1].geometries as number) - (start.geometries ?? 0),
    'geometry growth after five switches back to the starting area'
  ).toBeLessThanOrEqual(LIMIT.maxGeometryGrowth);
  expect(perHop[perHop.length - 1].webglContexts ?? 0, 'live WebGL contexts after five switches').toBeLessThanOrEqual(
    LIMIT.maxContexts
  );

  // One more pass over Bandra, so its first and second visits are comparable
  // directly. Everything before this was a different area each time.
  await reset(page, 'five-cycle bandra revisit');
  await switchAreaAndWait(page, 'Bandra West');
  await page.waitForTimeout(6000);
  const bandraSecond = await snapshot(page);
  const bandraFirst = perHop[0];
  report.fiveCycleBandraRevisit = {
    note: 'Bandra West is wholly live OSM; two visits to it differ only if state is retained',
    geometriesFirstVisit: bandraFirst.geometries,
    geometriesSecondVisit: bandraSecond.geometries,
    drawCallsFirstVisit: bandraFirst.drawCalls,
    drawCallsSecondVisit: bandraSecond.drawCalls,
  };
  expect(
    (bandraSecond.geometries ?? 0) - (bandraFirst.geometries as number),
    'geometry growth between two visits to Bandra West'
  ).toBeLessThanOrEqual(LIMIT.maxGeometryGrowth);

  await page.screenshot({ path: join(ARTIFACT_DIR, 'gate-6-area-after-5-switches.png') });
});

// ---------------------------------------------------------------------------
// Typing: the invalidation bug
// ---------------------------------------------------------------------------
test('gate: typing a coordinate does not rebuild the scene', async ({ page }) => {
  await page.goto('/app/map?view=3d&perf=1');
  await waitForScene(page);
  const before = await snapshot(page);

  // The Latitude field in the area menu. Phase 0 measured 100-183 ms per
  // keystroke here, twice, because MapPage built overlayModel as a literal and
  // PrecinctMap3D's scene effect depended on it.
  // The labels are sibling <label> elements with no htmlFor, so the fields are
  // addressed positionally within the menu: Lat, Lon, m.
  await openAreaMenu(page);
  const fields = page.locator('input[type="number"]');
  await expect(fields).toHaveCount(3);
  const field = fields.nth(0);

  // The area menu is open over the map, so an idle window here is the honest
  // comparison for what typing costs.
  const idle = await idleBaseline(page, 3000);
  await reset(page, 'type-coordinate');
  const chars = ['1', '2', '3', '4', '5', '6'];
  for (const c of chars) {
    await field.fill('');
    await field.type(c, { delay: 40 });
  }
  await page.waitForTimeout(1000);

  const after = await snapshot(page);
  const typing = {
    keystrokes: chars.length,
    idleBaseline: idle,
    maxFrameMs: Math.round(after.maxFrameMs),
    maxFrameMsOverIdle: Math.round(after.maxFrameMs) - idle.maxFrameMs,
    longFrames: after.longFrames,
    sceneBuildsBefore: before.sceneBuilds,
    sceneBuildsAfter: after.sceneBuilds,
  };
  report.typing = typing;

  await page.screenshot({ path: join(ARTIFACT_DIR, 'gate-2-after-typing.png') });

  // The point of the fix: the value of the field changes on every keystroke, so
  // if the scene effect still depends on anything derived from it, the build
  // count climbs. It must not.
  expect(after.sceneBuilds, 'scene rebuilds caused by typing').toBe(before.sceneBuilds);
  expect(typing.maxFrameMsOverIdle, 'worst frame while typing, over idle').toBeLessThan(
    LIMIT.idleInteractionExtraFrameMs
  );
});

// ---------------------------------------------------------------------------
// Layer toggles: the invalidation bug, second half
// ---------------------------------------------------------------------------
test('gate: toggling a layer does not rebuild the scene', async ({ page }) => {
  await page.goto('/app/map?view=3d&perf=1');
  await waitForScene(page);
  const before = await snapshot(page);

  // "Labels" is a checkbox in the layer panel. It used to be a dependency of the
  // scene-construction effect, so unticking it disposed and rebuilt every mesh to
  // change one boolean. The panel is collapsed by default, so open it first.
  await page.locator('button').filter({ hasText: /^Layers$/ }).first().click();
  const labelsToggle = page.locator('button').filter({ hasText: /^Labels$/ }).first();
  await labelsToggle.waitFor({ state: 'visible', timeout: 20_000 });

  const idle = await idleBaseline(page, 3000);
  await reset(page, 'toggle-layer');
  for (let i = 0; i < 3; i++) {
    await labelsToggle.click();
    await page.waitForTimeout(250);
  }
  await page.waitForTimeout(500);

  const after = await snapshot(page);
  const layerToggling = {
    toggles: 3,
    idleBaseline: idle,
    maxFrameMs: Math.round(after.maxFrameMs),
    maxFrameMsOverIdle: Math.round(after.maxFrameMs) - idle.maxFrameMs,
    longFrames: after.longFrames,
    sceneBuildsBefore: before.sceneBuilds,
    sceneBuildsAfter: after.sceneBuilds,
  };
  report.layerToggling = layerToggling;

  expect(after.sceneBuilds, 'scene rebuilds caused by layer toggles').toBe(before.sceneBuilds);
  expect(layerToggling.maxFrameMsOverIdle, 'worst frame while toggling a layer, over idle').toBeLessThan(
    LIMIT.idleInteractionExtraFrameMs
  );
});

// ---------------------------------------------------------------------------
// Hidden views: a backgrounded or scrolled-away map should not render
// ---------------------------------------------------------------------------
test('gate: unmounting the 3d view hands back its WebGL context', async ({ page }) => {
  await page.goto('/app/map?view=3d&perf=1');
  await waitForScene(page);
  const before = await snapshot(page);
  expect(before.geometries ?? 0, 'the 3d scene should hold GPU geometry').toBeGreaterThan(0);
  expect(before.webglContexts ?? 0, 'the 3d view should hold a context').toBeGreaterThan(0);

  // Switch view in-app. A page.goto here would reload the document and reset the
  // probe, which would measure the new page rather than the teardown.
  await page.getByRole('button', { name: /2D Cadastre Atlas/i }).click();
  await expect(page.locator('canvas').first()).toHaveCount(1, { timeout: 30_000 });
  await page.waitForTimeout(3000);
  const after = await snapshot(page);

  report.unmount = {
    geometriesBefore: before.geometries,
    webglContextsBefore: before.webglContexts,
    webglContextsAfterUnmount: after.webglContexts,
    geometriesAfterUnmount: after.geometries,
  };

  // The 3D context has to come back before the incoming view claims one. The 2D
  // Cadastre Atlas is MapLibre, which is itself WebGL, so the count after the
  // switch is 1, not 0. What must not happen is 2: the three.js context
  // surviving its own unmount. dispose() alone does not release it, Chrome keeps
  // handing out contexts until roughly 16 are outstanding, and past that
  // WebGLRenderer construction fails silently and presents as a blank canvas.
  // The counter is driven by a webglcontextlost listener, so this is the browser
  // reporting release rather than the app asserting it about itself.
  expect(after.webglContexts ?? 0, 'live WebGL contexts after switching away from 3D').toBe(1);
});

// ---------------------------------------------------------------------------
// Console hygiene: a green performance run that logs errors is not a pass
// ---------------------------------------------------------------------------
test('gate: no console errors across the map views', async ({ page }) => {
  for (const view of ['3d', '2d', 'cadastre', 'open_twin']) {
    await page.goto(`/app/map?view=${view}`);
    await page.waitForTimeout(2500);
  }
  // React logs recoverable errors through console.error, so anything collected
  // here is a real defect even when the app still renders.
  report.consoleErrors = consoleErrors;
  expect(consoleErrors, 'console errors').toEqual([]);
});
