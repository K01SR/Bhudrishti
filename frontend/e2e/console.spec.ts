import { expect, test } from '@playwright/test';

/**
 * The system console is the one screen whose job is to state what is actually
 * measured. That makes it worth a test, because the failure mode is silent and
 * attractive: a field is added to the panel, it looks plausible, and an
 * unmeasured value becomes an authoritative-looking figure again.
 *
 * The backend's `/osm/summary` is a live example. It genuinely computes road
 * length, streetlight and tree counts and POI totals, and it also returns a
 * block of literals: civic counts all pinned to 1, and a
 * `geospatial_accuracy` section claiming RTK-grade closure error against a
 * Survey of India datum. The console shows the first group and withholds the
 * second. These assertions are what keep the second from creeping back in.
 */
test.describe('system console', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/app/console');
    await expect(page.locator('h1')).toContainText('System Console');
    // Wait for the data panels rather than a fixed delay.
    await expect(page.getByText('Buildings held')).toBeVisible({ timeout: 20_000 });
  });

  test('renders measured figures without console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (m) => {
      if (m.type() === 'error') errors.push(m.text());
    });
    page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));

    await page.reload();
    await expect(page.getByText('Buildings held')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText('Regions cached')).toBeVisible();

    // Authoritative regions is a real 0 for this deployment, and it is the
    // number that matters most: it says the platform holds no government-graded
    // source, which is why OSM-derived figures are labelled as such elsewhere.
    await expect(page.getByText('Authoritative regions')).toBeVisible();
    await expect(page.getByText('not reported by this endpoint')).toHaveCount(0);

    expect(errors, 'console should be clean').toEqual([]);
  });

  test('withholds figures the backend does not actually measure', async ({ page }) => {
    // The explanatory notes name the withheld fields, which is deliberate: a
    // reader should be able to see that something was withheld and why. So the
    // assertion runs against the page with those notes removed, and then checks
    // separately that the notes are present.
    const dataText = await page.evaluate(() => {
      const clone = document.body.cloneNode(true) as HTMLElement;
      clone.querySelectorAll('[data-testid="swiss-unverified-note"]').forEach((n) => n.remove());
      return clone.innerText.toLowerCase();
    });

    // The fabricated survey-grade claim, and the numeric form of it.
    expect(dataText, 'survey-grade positioning claim must not be presented as a figure').not.toContain('survey grade');
    expect(dataText, 'RTK closure error must not be presented as a figure').not.toContain('rtk closure error');
    expect(dataText).not.toMatch(/\d+(\.\d+)?\s*mm/);
    expect(dataText, 'the Survey of India datum claim must not be presented as fact').not.toContain('elevation datum');

    // The civic counts that are hardcoded to 1 each.
    for (const claim of ['ward office', 'health clinic', 'police post', 'ev charging', 'substation', 'transit shelter']) {
      expect(dataText, `"${claim}" is a hardcoded literal and must not be shown as data`).not.toContain(claim);
    }

    // The exclusion has to be visible, not silent: a reader should be able to
    // tell that fields were withheld on purpose. There is more than one note
    // (authoritative regions, and the precinct fabric), so this asserts on the
    // first rather than requiring exactly one.
    await expect(page.getByText(/not measured/i).first()).toBeVisible();
  });

  test('shows the computed fabric figures it does trust', async ({ page }) => {
    const body = (await page.locator('body').innerText()).toLowerCase();
    expect(body).toContain('total roads km');
    expect(body).toContain('streetlights installed');
    expect(body).toContain('shade trees planted');
    expect(body).toContain('total pois');
  });
});
