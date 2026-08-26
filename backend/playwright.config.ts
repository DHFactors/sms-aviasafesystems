import { defineConfig } from '@playwright/test';
import path from 'path';

const PUBLIC_DIR = path.resolve(__dirname, '..', 'public');

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: 'http://localhost:5500',
    headless: true,
  },
  webServer: {
    command: `python -m http.server 5500 --directory "${PUBLIC_DIR}"`,
    port: 5500,
    reuseExistingServer: true,
    timeout: 10_000,
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
