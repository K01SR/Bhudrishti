import { defineConfig, devices } from '@playwright/test';

/**
 * The repo had no browser test infrastructure of any kind: no config, no `test`
 * script, no screenshot harness. `tests/frontend_source.py` scrapes source text
 * and cannot observe a frame, so the map acceptance gates had no way to be
 * checked. This config exists to make the gates executable.
 *
 * The WebGL args matter. Headless Chromium has no GPU here, so WebGL only works
 * through SwiftShader; without these the 3D and LiDAR views render a blank
 * canvas and every measurement reads as a pass.
 */
const CHROMIUM_ARGS = [
  '--use-gl=angle',
  '--use-angle=swiftshader',
  '--enable-unsafe-swiftshader',
  '--ignore-gpu-blocklist',
  '--no-sandbox',
  '--disable-dev-shm-usage',
];

export default defineConfig({
  testDir: './e2e',
  outputDir: './e2e/.artifacts',
  // A stall-gate suite waits on live backend and Overpass responses, which are
  // slower and far more variable than local rendering.
  timeout: 180_000,
  expect: { timeout: 30_000 },
  // The Phase 1 gate loads areas repeatedly; running that in parallel would have
  // the workers competing for the one SwiftShader context and corrupt the frame
  // timings being measured.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [
    ['list'],
    ['json', { outputFile: './e2e/.artifacts/results.json' }],
  ],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
    trace: 'retain-on-failure',
    video: 'off',
    screenshot: 'only-on-failure',
    actionTimeout: 30_000,
    navigationTimeout: 60_000,
    launchOptions: { args: CHROMIUM_ARGS },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1024 } },
    },
  ],
});
