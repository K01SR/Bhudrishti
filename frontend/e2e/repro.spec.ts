import { expect, test, type Page } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
// Pulls in the `window.__PERF__` global declaration.
import type { PerfMetrics } from '../src/perf/perf';

/**
 * Phase 0 reproduction suite.
 *
 * This is a diagnostic, not a gate. Each test drives one of the four reported
 * issues, collects the evidence the report needs, and writes it to
 * `e2e/.artifacts/phase0-report.json`. The assertions only check that evidence
 * was gathered, never that the bug is still present, so the suite stays green
 * once Phase 1 fixes the freezes. Phase 1 replaces the numbers with thresholds.
 */

type Snapshot = PerfMetrics;

type Stall = { durationMs: number; at: number; label: string };

const report: Record<string, unknown> = {};
// package.json is "type": "module", so __dirname is not defined.
const artifactDir = join(import.meta.dirname, '.artifacts');

function flush() {
  mkdirSync(artifactDir, { recursive: true });
  writeFileSync(join(artifactDir, 'phase0-report.json'), JSON.stringify(report, null, 2));
}

async function snapshot(page: Page): Promise<Snapshot> {
  return page.evaluate(() => {
    const p = window.__PERF__;
    if (!p) throw new Error('perf probe missing: load the page with ?perf=1');
    // Detach from the live store: the longFrames log and the counters keep
    // mutating while the assertion reads them.
    return { ...p.metrics };
  });
}

async function stalls(page: Page): Promise<Stall[]> {
  return page.evaluate(() => {
    const p = window.__PERF__;
    return p ? p.longFrames.map((f) => ({ ...f })) : [];
  });
}

async function reset(page: Page, label = '') {
  await page.evaluate((l: string) => {
    window.__PERF__?.reset();
    window.__PERF__?.label(l);
  }, label);
}

/** The area control reads "Airoli Sector-8 precinct" before a load and
 * "Anywhere: <name> - <source>" after one, so match on either. */
async function openAreaMenu(page: Page) {
  const toggle = page
    .locator('button')
    .filter({ hasText: /Anywhere:|Airoli Sector-8 precinct/i })
    .first();
  await toggle.waitFor({ state: 'visible', timeout: 30_000 });
  await toggle.click();
  await page.getByRole('button', { name: 'Airoli S8', exact: true }).waitFor({ state: 'visible' });
}

/** Settle the page after a navigation: wait for the canvas and for a few frames. */
async function settle(page: Page, frames = 12) {
  await page.waitForTimeout(400);
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

const consoleErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  consoleErrors.length = 0;
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text());
  });
  page.on('pageerror', (e) => consoleErrors.push(`pageerror: ${e.message}`));
});

test.afterAll(() => flush());

// ---------------------------------------------------------------------------
// Issue 1: /app/map?view=3d freezes after loading a different area.
// ---------------------------------------------------------------------------
test('issue 1: 3d view frame cost when switching areas', async ({ page }) => {
  await page.goto('/app/map?view=3d&perf=1');
  await settle(page, 30);
  const before = await snapshot(page);

  // Open the area menu and walk Airoli -> Pune -> Delhi, which is the sequence
  // in the reported freeze.
  await openAreaMenu(page);

  const hops = ['Pune Shivajinagar', 'Bengaluru MG Rd', 'Airoli S8'];
  const perHop: Array<Record<string, unknown>> = [];

  for (const hop of hops) {
    await reset(page, `load-area ${hop}`);
    await page.getByRole('button', { name: hop, exact: true }).click();
    // The area request goes to the backend and then rebuilds the three.js scene.
    await page.waitForTimeout(6000);
    const s = await snapshot(page);
    const stallsHere = await stalls(page);
    perHop.push({
      hop,
      sceneBuildMs: Math.round(s.sceneBuildMs),
      areaLoadMs: Math.round(s.areaLoadMs),
      maxFrameMs: Math.round(s.maxFrameMs),
      longFrames: s.longFrames,
      drawCalls: s.drawCalls,
      geometries: s.geometries,
      webglContexts: s.webglContexts,
      heapMB: s.heapMB === null ? null : Math.round(s.heapMB),
      worstStalls: stallsHere
        .slice()
        .sort((a, b) => b.durationMs - a.durationMs)
        .slice(0, 5)
        .map((f) => ({ ms: Math.round(f.durationMs), label: f.label })),
    });
  }

  report.issue1_areaSwitch = {
    initial: {
      maxFrameMs: Math.round(before.maxFrameMs),
      drawCalls: before.drawCalls,
      geometries: before.geometries,
      webglContexts: before.webglContexts,
    },
    perHop,
    consoleErrors: consoleErrors.slice(0, 10),
  };
  flush();

  expect(perHop.length).toBe(hops.length);
  await page.screenshot({ path: join(artifactDir, 'issue1-after-area-switch.png') });
});

// ---------------------------------------------------------------------------
// Issue 1b: typing in the lat/lon inputs re-renders MapPage, which rebuilds the
// scene because overlayModel is a fresh object literal each render.
// ---------------------------------------------------------------------------
test('issue 1b: scene rebuild cost on a single keystroke', async ({ page }) => {
  await page.goto('/app/map?view=3d&perf=1');
  await settle(page, 30);
  await openAreaMenu(page);

  const latBox = page.locator('input[type="number"]').first();
  await latBox.waitFor();

  await reset(page, 'keystroke in lat input');
  const start = await snapshot(page);
  const startGeoms = start.geometries;

  // Six keystrokes. Each setState re-renders MapPage, and MapPage's
  // overlayModel literal is a dependency of the scene effect.
  for (const ch of ['1', '2', '3', '4', '5', '6']) {
    await latBox.press('End');
    await latBox.type(ch, { delay: 60 });
    await page.waitForTimeout(250);
  }

  const after = await snapshot(page);
  const stallList = await stalls(page);

  report.issue1b_keystroke = {
    sceneBuildMs: Math.round(after.sceneBuildMs),
    maxFrameMs: Math.round(after.maxFrameMs),
    longFrames: after.longFrames,
    geometriesBefore: startGeoms,
    geometriesAfter: after.geometries,
    webglContexts: after.webglContexts,
    stalls: stallList.map((f) => ({ ms: Math.round(f.durationMs), label: f.label })),
  };
  flush();

  expect(after.frames).toBeGreaterThan(0);
});

// ---------------------------------------------------------------------------
// Issue 2: /app/properties/X-OSM-5253660C LiDAR view freezes or stays empty.
// ---------------------------------------------------------------------------
test('issue 2: LiDAR view on an OSM-sourced property', async ({ page }) => {
  const apiCalls: Array<{ url: string; status: number; body: string }> = [];
  page.on('response', async (r) => {
    const u = r.url();
    if (!u.includes('/api/v1/')) return;
    if (!/lidar|parcels|properties/.test(u)) return;
    let body = '';
    try {
      body = (await r.text()).slice(0, 600);
    } catch {
      body = '<unreadable>';
    }
    apiCalls.push({ url: u.replace(/^https?:\/\/[^/]+/, ''), status: r.status(), body });
  });

  await page.goto('/app/properties/X-OSM-5253660C?perf=1');
  await settle(page, 20);

  const onLoad = await snapshot(page);
  const pageText = (await page.locator('body').innerText()).slice(0, 1200);

  // The LiDAR tab is opened by a button gated on permissions, so look for it
  // rather than assuming a label.
  const lidarButton = page.getByRole('button', { name: /lidar/i }).first();
  const hasLidarButton = await lidarButton.count().then((n) => n > 0).catch(() => false);

  let afterOpen: Snapshot | null = null;
  if (hasLidarButton) {
    await reset(page, 'open lidar inspector');
    await lidarButton.click();
    await page.waitForTimeout(9000);
    afterOpen = await snapshot(page);
    await page.screenshot({ path: join(artifactDir, 'issue2-lidar-open.png') });
  }

  report.issue2_lidar = {
    url: '/app/properties/X-OSM-5253660C',
    hasLidarButton,
    onLoad: {
      maxFrameMs: Math.round(onLoad.maxFrameMs),
      longFrames: onLoad.longFrames,
      webglContexts: afterOpen?.webglContexts ?? null,
    },
    afterOpen: afterOpen
      ? {
          maxFrameMs: Math.round(afterOpen.maxFrameMs),
          longFrames: afterOpen.longFrames,
          drawCalls: afterOpen.drawCalls,
          triangles: afterOpen.triangles,
          features: afterOpen.features,
          heapMB: afterOpen.heapMB === null ? null : Math.round(afterOpen.heapMB),
        }
      : null,
    apiCalls,
    renderedText: pageText,
    consoleErrors: consoleErrors.slice(0, 10),
  };
  flush();

  expect(apiCalls.length).toBeGreaterThan(0);
});

// ---------------------------------------------------------------------------
// Issue 3: a tile or logo saying a key is required appears on the map.
// Inventory every tile-ish request the app makes, per view.
// ---------------------------------------------------------------------------
test('issue 3: tile host inventory and placeholder hunt', async ({ page }) => {
  const hosts = new Map<string, { count: number; samples: string[]; statuses: number[] }>();
  const images: Array<{ url: string; status: number; contentType: string; bytes: number }> = [];

  page.on('response', async (r) => {
    const u = r.url();
    const ct = (r.headers()['content-type'] || '').toLowerCase();
    const isImage = ct.startsWith('image/');
    // Tile traffic: raster tiles, vector tiles, or anything off the app origin.
    const looksLikeTile =
      /\.(png|jpe?g|webp|pbf|mvt)(\?|$)/i.test(u) ||
      /basemaps\.cartocdn|arcgisonline|tile\.openstreetmap|openfreemap|protomaps|stadia|thunderforest|maptiler|mapbox/i.test(u);
    if (!isImage && !looksLikeTile) return;
    if (u.startsWith('data:')) return;

    const host = (() => {
      try {
        return new URL(u).host;
      } catch {
        return 'unparseable';
      }
    })();
    const rec = hosts.get(host) || { count: 0, samples: [], statuses: [] };
    rec.count += 1;
    if (rec.samples.length < 3) rec.samples.push(u.replace(host, '<host>').slice(0, 160));
    rec.statuses.push(r.status());
    hosts.set(host, rec);

    if (isImage) {
      let bytes = 0;
      try {
        bytes = (await r.body()).length;
      } catch {
        bytes = -1;
      }
      images.push({ url: u.replace(host, '<host>').slice(0, 160), status: r.status(), contentType: ct, bytes });
    }
  });

  // A placeholder tile is usually a small solid-colour PNG. Flag any tiny
  // successful image so a reviewer can eyeball it.
  const suspicious = images.filter((i) => i.status === 200 && i.bytes > 0 && i.bytes < 4096);

  const views: Array<Record<string, unknown>> = [];
  for (const view of ['cadastre', 'open_twin', 'satellite']) {
    await page.goto(`/app/map?view=${view}&perf=1`);
    await settle(page, 20);
    await page.waitForTimeout(3500);
    views.push({
      view,
      hosts: Object.fromEntries(hosts),
      imageCount: images.length,
      suspiciousSmallImages: suspicious.slice(0, 20),
    });
    await page.screenshot({ path: join(artifactDir, `issue3-view-${view}.png`) });
  }

  report.issue3_tiles = {
    views,
    // Any occurrence of key/subscription wording in the rendered page.
    keyWordsInDom: await page.evaluate(() => {
      const t = document.body.innerText;
      return (t.match(/.{0,40}(api[\s_-]?key|access blocked|requires? (an )?(api )?key|token required|upgrade to|unauthorized).{0,40}/gi) || []).slice(0, 10);
    }),
    consoleErrors: consoleErrors.slice(0, 10),
  };
  flush();

  expect(views.length).toBe(3);
});

// ---------------------------------------------------------------------------
// Issue 4: a property link opens /app/properties/Y0B6YWPJVLTYGR and the API
// returns 404 "no dataset ingested for this identifier".
// ---------------------------------------------------------------------------
test('issue 4: the not-found identifier path', async ({ page }) => {
  const calls: Array<{ url: string; status: number; body: string }> = [];
  page.on('response', async (r) => {
    const u = r.url();
    if (!u.includes('/api/v1/parcels/')) return;
    let body = '';
    try {
      body = (await r.text()).slice(0, 900);
    } catch {
      body = '<unreadable>';
    }
    calls.push({ url: u.replace(/^https?:\/\/[^/]+/, ''), status: r.status(), body });
  });

  await page.goto('/app/properties/Y0B6YWPJVLTYGR?perf=1');
  await settle(page, 20);

  const rendered = (await page.locator('body').innerText()).slice(0, 1500);
  await page.screenshot({ path: join(artifactDir, 'issue4-not-found.png') });

  report.issue4_notFound = {
    url: '/app/properties/Y0B6YWPJVLTYGR',
    apiCalls: calls,
    renderedText: rendered,
    // If the raw JSON detail object is being dumped into the page, that is the
    // user-visible half of the bug and it is trivially detectable here.
    rendersRawJson: /"not_available"|no dataset ingested for this identifier/.test(rendered),
    consoleErrors: consoleErrors.slice(0, 10),
  };
  flush();

  expect(calls.length).toBeGreaterThan(0);

  // The backend answers an unknown identifier with a structured explanation -
  // an `explanation` sentence and a `not_available` list saying which parts of
  // the record are missing and why, and which endpoint to use instead. The page
  // used to reach the user as a minified JSON blob, because the client
  // stringified the object rather than reading it.
  const notFound = calls.find((c) => c.status === 404);
  expect(notFound, 'the unknown identifier should 404 rather than fall back to invented geometry').toBeTruthy();
  expect(
    rendered,
    'the page must not dump the raw error object; the explanation and the not-available list are written for people'
  ).not.toMatch(/"not_available"|\{"error":/);

  // The parts worth having on screen, and the reason there is no geometry.
  expect(rendered, 'the not-found reason should be stated in words').toMatch(
    /no cadastral record|not available for this identifier/i
  );
  expect(
    rendered,
    'the page should say what is missing, not just that something is'
  ).toMatch(/parcel boundary|land-record|floor ownership/i);
  // Pointing at the endpoint that does work is the difference between a dead
  // end and a next step.
  expect(
    rendered,
    'the not-found page should route the user to the endpoint that does resolve areas'
  ).toMatch(/opendata\/area|ingest-area|any area/i);
});

test('issue 5: a canonical 3D identifier resolves instead of dead-ending', async ({ page }) => {
  // A canonical 3D ID is `ULPIN/UB17-L05-501-W`, and its `/` is a path separator,
  // so `/parcels/{ulpin}` could not address one: the request matched no route and
  // answered a bare `{"detail": "Not Found"}` with no explanation at all. The UI
  // mints exactly that form, so it could produce an identifier it could not
  // resolve. The resolver takes the whole identifier and returns the parent
  // parcel, the route, and an honest account of what is or is not ingested.
  const calls: Array<{ url: string; status: number; body: string }> = [];
  page.on('response', async (r) => {
    const u = r.url();
    if (!u.includes('/api/v1/ids/resolve') && !u.includes('/api/v1/parcels/')) return;
    let body = '';
    try {
      body = (await r.text()).slice(0, 900);
    } catch {
      body = '<unreadable>';
    }
    calls.push({ url: u.replace(/^https?:\/\/[^/]+/, ''), status: r.status(), body });
  });

  // Pick a parcel that is actually in the store rather than hard-coding one, so
  // the test states the routing contract instead of depending on a fixture ULPIN
  // left behind by an earlier ingest.
  const list = await page.request.get('/api/v1/parcels/');
  expect(list.ok(), 'the cadastral store should be reachable').toBeTruthy();
  const parcels = (await list.json()) as Array<{ ulpin?: string }>;
  const parentUlpIn = parcels.find((p) => typeof p.ulpin === 'string' && p.ulpin.length > 0)?.ulpin;
  expect(parentUlpIn, 'at least one real parcel must be ingested to test routing against').toBeTruthy();

  const composite = `${parentUlpIn}%2FUB17-L05-501-W`;
  await page.goto(`/app/properties/${composite}`, { waitUntil: 'domcontentloaded' });
  await settle(page, 25);

  const rendered = (await page.locator('body').innerText()).slice(0, 1800);
  await page.screenshot({ path: join(artifactDir, 'issue5-3d-id-resolution.png') });

  report.issue5_threeDId = {
    url: `/app/properties/${composite}`,
    parent_ulpin: parentUlpIn,
    apiCalls: calls,
    renderedText: rendered,
    rendersRawJson: /\{"error":|"not_available"/.test(rendered),
  };
  flush();

  const resolveCall = calls.find((c) => c.url.includes('/ids/resolve'));
  expect(resolveCall, 'the resolver should be consulted for a composite identifier').toBeTruthy();
  expect(resolveCall!.status, 'a real parent parcel should resolve, not 404').toBe(200);

  const body = JSON.parse(resolveCall!.body || '{}');
  expect(body.parent_ulpin, 'the parent parcel is the part that exists').toBe(parentUlpIn);
  expect(body.route, 'the resolver should hand back a route the UI can follow').toBe(
    `/app/properties/${parentUlpIn}?unit=UB17-L05-501-W`
  );
  // Existence and syntax are separate claims, and the unit was never ingested.
  expect(body.exists, 'an unbuilt unit is not a resolved identifier').toBe(false);
  expect(body.unresolved?.building_code, 'the unit that was asked for is named').toBe('UB17-L05-501-W');

  // The page loads the parcel and states that the requested unit is not on it,
  // rather than rendering the parcel as though it were.
  expect(rendered, 'the unbuilt unit should be called out, not silently dropped').toMatch(
    /not part of any ingested structure|is not recorded on this parcel/i
  );
  expect(rendered, 'the page must not dump the raw error object').not.toMatch(/\{"error":/);
});
