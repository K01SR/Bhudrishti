import { test, expect } from '@playwright/test';

/**
 * The atlas sub-grade layer.
 *
 * The atlas carries no sub-grade geometry of its own - structures arrive as
 * footprints, floors and a height - so this layer is opt-in and depends on a
 * record that mostly does not exist. The tests below are as much about what
 * the layer refuses to do as about what it draws: an empty result must stay
 * empty, and whatever is drawn must be labelled with its provenance.
 */
test.describe('2D cadastre atlas: underground option', () => {
  test('the option is opt-in and adds no request until it is opened', async ({ page }) => {
    const calls: string[] = [];
    page.on('request', (r) => {
      if (r.url().includes('/subgrade')) calls.push(r.url());
    });

    await page.goto('/app/map?view=cadastre', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(9000);

    await expect(page.getByTestId('atlas-underground-toggle')).toBeVisible();
    // Loading this for every atlas view would tax every session for a layer
    // most of them never open.
    expect(calls).toHaveLength(0);
    await expect(page.getByTestId('atlas-underground-status')).toHaveCount(0);
  });

  test('opening it fetches once, not on every render', async ({ page }) => {
    const calls: string[] = [];
    page.on('request', (r) => {
      if (r.url().includes('/subgrade')) calls.push(r.url());
    });

    await page.goto('/app/map?view=cadastre', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(9000);
    await page.getByTestId('atlas-underground-toggle').click();
    await expect(page.getByTestId('atlas-underground-status')).toBeVisible();
    await page.waitForTimeout(2500);

    expect(calls).toHaveLength(1);
  });

  test('it states what it drew, and that it is not surveyed', async ({ page }) => {
    await page.goto('/app/map?view=cadastre', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(9000);
    await page.getByTestId('atlas-underground-toggle').click();

    const status = page.getByTestId('atlas-underground-status');
    await expect(status).toBeVisible();
    const text = await status.innerText();

    if (/no sub-grade record/i.test(text)) {
      // The honest empty case: nothing drawn, and the reason given.
      expect(text).not.toMatch(/\d+\s+units? at or below/i);
    } else {
      // Whatever is drawn must say how deep and must not imply a survey.
      expect(text).toMatch(/\d+\s+units? at or below datum/i);
      expect(text).toMatch(/not surveyed/i);
    }
  });

  test('switching it off leaves no layer behind', async ({ page }) => {
    await page.goto('/app/map?view=cadastre', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(9000);

    const toggle = page.getByTestId('atlas-underground-toggle');
    await toggle.click();
    await expect(page.getByTestId('atlas-underground-status')).toBeVisible();
    await toggle.click();

    await expect(page.getByTestId('atlas-underground-status')).toHaveCount(0);
    await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  });
});
