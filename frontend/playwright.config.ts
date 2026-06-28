import { defineConfig, devices } from "@playwright/test";

// E2E config. Spins up a self-contained mock backend (port 8000) and the Next
// dev server (port 3000) pointed at it, then runs specs on desktop + mobile.
const BASE_URL = "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 5"] } },
  ],
  webServer: [
    {
      command: "node e2e/mock-server.mjs",
      port: 8000,
      reuseExistingServer: !process.env.CI,
      stdout: "ignore",
    },
    {
      command: "npm run dev",
      port: 3000,
      reuseExistingServer: !process.env.CI,
      env: { NEXT_PUBLIC_API_URL: "http://localhost:8000" },
      timeout: 120_000,
    },
  ],
});
