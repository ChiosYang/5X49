import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e', testMatch: '**/*.spec.ts', workers: 1, fullyParallel: false,
  retries: 0, timeout: 60000, expect: { timeout: 15000 },
  outputDir: 'test-results', reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: process.env.E2E_BASE_URL, viewport: { width: 390, height: 844 },
    hasTouch: true, screenshot: 'only-on-failure', trace: 'retain-on-failure',
    launchOptions: process.env.E2E_CHROMIUM_PATH ? { executablePath: process.env.E2E_CHROMIUM_PATH } : {} },
});
