import { test, expect } from "./fixtures/base";

const apiBase = process.env.PLAYWRIGHT_API_URL || "http://localhost:8000";

test.describe("backend API contract smoke tests", () => {
  test("important API endpoints return successful responses", async ({ request }) => {
    const endpoints = [
      "/health",
      "/api/monitor/pulse",
      "/api/monitor/completed",
      "/api/monitor/clients",
      "/api/monitor/alerts",
      "/api/ingest/documents",
    ];

    for (const endpoint of endpoints) {
      const response = await request.get(`${apiBase}${endpoint}`);
      expect(response.ok(), `${endpoint} returned ${response.status()}`).toBeTruthy();
    }
  });
});
