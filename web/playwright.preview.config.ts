import { defineConfig, devices } from "@playwright/test";

// The same smoke tests against a deployed preview, plus e2e-live (real API, 1 live question):
//   BASE_URL=https://<preview>.vercel.app VERCEL_AUTOMATION_BYPASS_SECRET=... npx playwright test -c playwright.preview.config.ts
// The secret is the project's existing "Protection Bypass for Automation" value; never commit it.
const secret = process.env.VERCEL_AUTOMATION_BYPASS_SECRET;

export default defineConfig({
  testMatch: ["e2e/**/*.spec.ts", "e2e-live/**/*.spec.ts"],
  fullyParallel: true,
  reporter: [["list"]],
  use: {
    baseURL: process.env.BASE_URL,
    trace: "retain-on-failure",
    extraHTTPHeaders: secret ? { "x-vercel-protection-bypass": secret, "x-vercel-set-bypass-cookie": "true" } : {},
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
