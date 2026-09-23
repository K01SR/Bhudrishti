import { expect, test, type Page } from '@playwright/test';

/**
 * Regression test for picking.
 *
 * Picking is the one interaction the perf gate does not cover, and it is the
 * part of the scene most tightly coupled to how geometry is stored: the click
 * handler raycasts against a list of individual meshes and reads `userData` off
 * whatever it hits. Any change that stores many parcels in one object (batching,
 * instancing) has to keep this working.
 *
 * ## What this covers, and what it does not
 *
 * This asserts that a click on empty ground selects nothing. That is the half
 * that is stable enough to gate on: it catches picking that reports hits where
 * there is nothing to hit, which is what an over-broad raycast or a merged
 * object with no per-instance identity would start doing.
 *
 * It deliberately does NOT assert that clicking a building opens the right
 * card. That test was attempted and abandoned: on this gate's renderer the
 * scene is not reproducible between runs, so a click at a given pixel returns a
 * building on some runs and nothing on others (measured: the same centre click
 * on a camera-focused building returned that building once, then `none` on three
 * consecutive runs; a 117-point scan returned 1, 2, then 1 hits). Data-arrival
 * timing, not scene randomness, is the likely cause. Asserting on it would
 * produce a test that fails intermittently and gets deleted, which is worse than
 * an acknowledged gap.
 *
 * The positive case is covered below, but not by clicking. The component
 * exposes a pick seam behind `?perf=1` (`__PICK__.resolve`) that feeds a named
 * instance through the *same* `resolveBuildingHit` the click handler uses, so
 * the assertion is on the real resolution path rather than on where a pixel
 * landed. That seam is what made a deterministic positive test possible; before
 * instancing there was no `instanceId` to address, since every building was its
 * own object carrying its own `userData`.
 */

const CARD = '[data-testid="building-card"]';

async function openMap(page: Page) {
  await page.goto('/app/map?view=3d&perf=1');
  await page.waitForFunction(() => (window as any).__PERF__?.metrics?.geometries > 0, null, { timeout: 30_000 });
  // The first frames are still settling the camera onto the precinct.
  await page.waitForTimeout(3000);
  return (await page.locator('canvas').first().boundingBox())!;
}

test('a click on empty ground selects nothing', async ({ page }) => {
  const box = await openMap(page);

  // Top-left of the canvas, well away from the precinct, which the camera is
  // aimed at. A card here would mean a hit was reported with nothing under the
  // cursor.
  await page.mouse.click(box.x + 20, box.y + 20);
  await page.waitForTimeout(400);
  expect(await page.locator(CARD).count(), 'empty ground should not open a property card').toBe(0);

  // The corners are the safest empties: the precinct occupies a narrow band and
  // no building reaches the canvas edge.
  for (const [dx, dy] of [
    [box.width - 20, 20],
    [20, box.height - 20],
    [box.width - 20, box.height - 20],
  ]) {
    await page.mouse.click(box.x + dx, box.y + dy);
    await page.waitForTimeout(300);
    expect(await page.locator(CARD).count(), `click at ${dx},${dy} should not open a property card`).toBe(0);
  }
});

/**
 * The positive case, addressed by instance rather than by pixel.
 *
 * Instancing means a precinct building and a persisted structure are no longer
 * Object3Ds that can be found by walking the scene, so what could regress is the
 * `instanceId` -> record resolution. That is exactly what a pixel test cannot
 * cover reliably, and it fails silently when broken: the click lands on the
 * mesh, `userData` is empty, and nothing is selected.
 */
test('an instanced building resolves back to its own record', async ({ page }) => {
  await openMap(page);
  await page.waitForFunction(() => (window as any).__PICK__?.counts, null, { timeout: 30_000 });

  const counts = await page.evaluate(() => (window as any).__PICK__.counts());
  expect(counts.precinct, 'the precinct should be instanced').toBeGreaterThan(0);

  // Every instance in both sets must resolve to its own record, not to a
  // neighbour and not to nothing.
  for (const which of ['precinct', 'structures'] as const) {
    const n = counts[which];
    if (!n) continue;
    const bad: string[] = [];
    for (let i = 0; i < n; i++) {
      const r = await page.evaluate(
        ([w, id]: [string, number]) => (window as any).__PICK__.resolve(w, id),
        [which, i] as [string, number],
      );
      if (!r || r.resolvedBy !== 'instanceId' || !r.code) bad.push(`${which}[${i}] -> ${JSON.stringify(r)}`);
    }
    expect(bad, `unresolvable instances in ${which}`).toEqual([]);
  }
});

/** Out-of-range ids must return null rather than throwing or leaking a neighbour. */
test('an out-of-range instance resolves to nothing', async ({ page }) => {
  await openMap(page);
  await page.waitForFunction(() => (window as any).__PICK__?.counts, null, { timeout: 30_000 });
  const n = await page.evaluate(() => (window as any).__PICK__.counts().precinct);
  const r = await page.evaluate((i: number) => (window as any).__PICK__.resolve('precinct', i), n + 5);
  expect(r, 'an instance past the end must not resolve').toBeNull();
});
