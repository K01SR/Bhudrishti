import { expect, test, type Page } from '@playwright/test';

/**
 * Regression tests for the instanced scene.
 *
 * Precinct buildings and persisted structures are one `InstancedMesh` each, not
 * one mesh per unit. That is where the draw calls went (99 -> 66) and it changed
 * three things that used to be per-object and are now per-instance or
 * per-material, each of which can fail silently:
 *
 *   - epoch styling, which used to assign `mesh.material.color` and
 *     `mesh.position` and now writes instance colours and matrices;
 *   - the wireframe, which was a per-mesh material flag and is now one flag for
 *     the whole set, so a per-unit reading of it is meaningless;
 *   - hiding, which was `mesh.visible = false` and is now a zero-scale matrix,
 *     because an instance has no per-instance visibility.
 *
 * The assertions read the instance buffers directly through a seam enabled by
 * `?perf=1`. Asserting on rendered pixels was rejected for the same reason
 * `picking.spec.ts` rejects it: where things land on screen is not reproducible
 * across runs, and a test that flakes gets deleted rather than fixed.
 */

type Dump = { scale: number[]; color: string; wireframe: boolean; vis: boolean };

async function openMap(page: Page) {
  await page.goto('/app/map?view=3d&perf=1');
  await page.waitForFunction(() => (window as any).__PERF__?.metrics?.geometries > 0, null, { timeout: 30_000 });
  await page.waitForFunction(() => (window as any).__PICK__?.counts, null, { timeout: 30_000 });
  // The first frames are still settling the camera onto the precinct.
  await page.waitForTimeout(3000);
}

const dump = (page: Page, which: 'precinct' | 'structures', id: number): Promise<Dump | null> =>
  page.evaluate(([w, i]: [string, number]) => (window as any).__PICK__.dump(w, i), [which, id] as [string, number]);

const epochButton = (page: Page, year: string) =>
  page.locator('button').filter({ hasText: new RegExp('^' + year) }).first();

/** Index of the instance drawn for a given building code, or -1. */
async function indexOf(page: Page, code: string): Promise<number> {
  return page.evaluate((c: string) => {
    const p = (window as any).__PICK__;
    const n = p.counts().precinct;
    for (let i = 0; i < n; i++) {
      const r = p.resolve('precinct', i);
      if (r?.code === c) return i;
    }
    return -1;
  }, code);
}

test('the 2024 epoch draws buildings as amber foundation slabs', async ({ page }) => {
  await openMap(page);
  const i = await indexOf(page, 'B-01');
  expect(i, 'B-01 should be in the precinct').toBeGreaterThanOrEqual(0);

  await epochButton(page, '2024').click();
  await page.waitForTimeout(1500);
  const d = (await dump(page, 'precinct', i))!;

  // A foundation slab is a flat plate: full footprint, but flattened in height.
  expect(d.scale[0], '2024 should keep the footprint width').toBeGreaterThan(1);
  expect(d.scale[1], '2024 should keep the footprint depth').toBeGreaterThan(1);
  expect(d.wireframe, '2024 is the drone-survey epoch and is drawn as wireframe').toBe(true);
  expect(d.color, '2024 draws the amber slab').toBe('eab308');
});

test('the 2025 epoch draws buildings as blueprint volumes, still wireframe', async ({ page }) => {
  await openMap(page);
  const i = await indexOf(page, 'B-01');
  expect(i).toBeGreaterThanOrEqual(0);

  await epochButton(page, '2025').click();
  await page.waitForTimeout(1500);
  const d = (await dump(page, 'precinct', i))!;

  expect(d.color, '2025 draws the blueprint blue').toBe('38bdf8');
  expect(d.wireframe, '2025 is a sanctioned drawing, not a build').toBe(true);
  // Full height, unlike the 2024 slab: same footprint, not flattened.
  expect(d.scale[2], '2025 should be full height').toBeGreaterThan(1);
});

test('the 2026 epoch draws built form, and omits B-12 which has no 2026 record', async ({ page }) => {
  await openMap(page);
  const b01 = await indexOf(page, 'B-01');
  const b12 = await indexOf(page, 'B-12');
  expect(b01).toBeGreaterThanOrEqual(0);
  expect(b12, 'B-12 is the violation building').toBeGreaterThanOrEqual(0);

  await epochButton(page, '2026').click();
  await page.waitForTimeout(1500);

  const shown = (await dump(page, 'precinct', b01))!;
  expect(shown.wireframe, '2026 is as-built, so not wireframe').toBe(false);
  expect(shown.color, '2026 draws the type colour, not the epoch tint').not.toBe('eab308');

  // B-12 has no 2026 record, so it must not be drawn in that epoch. It used to
  // be `mesh.visible = false`; it is now a zero-scale matrix.
  const absent = (await dump(page, 'precinct', b12))!;
  expect(absent.scale, 'B-12 has no 2026 record and must be collapsed, not drawn').toEqual([0, 0, 0]);
});

test('B-12 returns in 2027, and the whole set is solid', async ({ page }) => {
  await openMap(page);
  const b12 = await indexOf(page, 'B-12');
  expect(b12).toBeGreaterThanOrEqual(0);

  await epochButton(page, '2027').click();
  await page.waitForTimeout(1500);
  const d = (await dump(page, 'precinct', b12))!;

  expect(d.scale.every((s) => s > 0), 'B-12 is back in 2027').toBe(true);
  expect(d.wireframe, '2027 is the present day').toBe(false);
  // B-12 is "Sector 8 Later-Epoch Slab", a slab whose change only appears in
  // the later epoch. It is NOT a violation building, and this suite must not
  // assert that it is.
  //
  // This line previously read `expect(d.color).toBe('ef4444')` with the comment
  // "B-12 is the VIOLATION building, which is red in the built epochs." That
  // was stale pre-Phase-0 drift: the generator used to carry APPROVED /
  // FLAGGED / UNDER_REVIEW / VIOLATION statuses, and Phase 0 removed them
  // because nothing in this repository can approve a building or declare one a
  // violation (synthetic_generator.py, spatial_pipelines.py). The renderer
  // moved on; this assertion did not, and had started asserting a regulatory
  // verdict the product no longer produces -- the test had become the
  // fabrication.
  //
  // There is no STATUS_COLORS map in the viewer at all: colour is by building
  // type, which is why the assertion above at the 2026 epoch already reads
  // "2026 draws the type colour, not the epoch tint". B-12 is a slab, so the
  // type colour is the slab purple. Asserting it keeps the epoch -> colour
  // mapping honest and fails loudly if a slab is ever silently recoloured.
  expect(d.color, 'B-12 is a slab, so it draws the slab type colour').toBe('8b5cf6');
});

test('the wireframe is a property of the epoch, not of an individual unit', async ({ page }) => {
  await openMap(page);
  // Same flag on every instance in a given epoch: it is one shared material, so
  // a per-unit reading would be meaningless and a half-applied change would
  // otherwise go unnoticed.
  for (const [year, wire] of [
    ['2024', true],
    ['2025', true],
    ['2026', false],
    ['2027', false],
  ] as const) {
    await epochButton(page, year).click();
    await page.waitForTimeout(1200);
    const flags = await page.evaluate(() => {
      const p = (window as any).__PICK__;
      const n = p.counts().precinct;
      const out: boolean[] = [];
      for (let i = 0; i < n; i++) out.push(p.dump('precinct', i).wireframe);
      return out;
    });
    expect(new Set(flags), `all units share one material in ${year}`).toEqual(new Set([wire]));
  }
});
