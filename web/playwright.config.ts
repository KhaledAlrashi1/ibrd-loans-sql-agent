import { defineConfig, devices } from "@playwright/test";

// Smoke test of the built page with /api mocked: `npm run build && npm run test:e2e`.
export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: { command: "npm run start -- -p 3100 -H 127.0.0.1", url: "http://127.0.0.1:3100", reuseExistingServer: false },
});
