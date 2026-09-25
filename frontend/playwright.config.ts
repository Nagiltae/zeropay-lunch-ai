import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.pw.ts',
  fullyParallel: false,
  retries: 0,
  reporter: 'list',
  outputDir: '/tmp/zeropay-lunch-mvp-e2e-playwright',
  use: {
    baseURL: 'http://127.0.0.1:3017',
    ...devices['Desktop Chrome'],
    headless: true,
    launchOptions: { channel: 'chromium' },
  },
})
