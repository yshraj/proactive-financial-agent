import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

function loadEnvFile(filePath: string) {
  if (!fs.existsSync(filePath)) return;
  const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const [key, ...valueParts] = trimmed.split("=");
    if (!process.env[key]) process.env[key] = valueParts.join("=");
  }
}

loadEnvFile(path.resolve(__dirname, ".env.test"));

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000";
const API_URL = process.env.PLAYWRIGHT_API_URL || "http://localhost:8000";
const appPort = new URL(BASE_URL).port || "3000";
const isLocal = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?/.test(BASE_URL);
const skipWebServer = process.env.E2E_SKIP_WEBSERVER === "true" || !isLocal;
const storageState = "tests/.auth/user.json";

export default defineConfig({
  testDir: "./tests",
  outputDir: "test-results",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: "auth",
      testMatch: /auth\.setup\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "chromium",
      dependencies: ["auth"],
      use: { ...devices["Desktop Chrome"], storageState },
    },
    {
      name: "firefox",
      dependencies: ["auth"],
      use: { ...devices["Desktop Firefox"], storageState },
    },
    {
      name: "webkit",
      dependencies: ["auth"],
      use: { ...devices["Desktop Safari"], storageState },
    },
    {
      name: "mobile-chromium",
      dependencies: ["auth"],
      use: { ...devices["Pixel 5"], storageState },
    },
  ],
  webServer: skipWebServer
    ? undefined
    : [
        {
          command: "node tests/mock-server.mjs",
          url: `${API_URL}/health`,
          reuseExistingServer: !process.env.CI,
          stdout: "ignore",
          stderr: "pipe",
          timeout: 30_000,
        },
        {
          command: `npm run dev -- -p ${appPort}`,
          url: BASE_URL,
          reuseExistingServer: !process.env.CI,
          env: {
            NEXT_PUBLIC_API_URL: API_URL,
            NEXT_PUBLIC_SUPABASE_URL: "",
            NEXT_PUBLIC_SUPABASE_ANON_KEY: "",
          },
          timeout: 120_000,
        },
      ],
});
