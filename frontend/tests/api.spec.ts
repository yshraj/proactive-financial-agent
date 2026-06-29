import { test, expect } from "./fixtures/base";

const apiBase = process.env.PLAYWRIGHT_API_URL || "http://localhost:8000";
const today = new Date().toISOString().slice(0, 10);

test.describe("backend API contract smoke tests", () => {
  test("important API endpoints return successful responses", async ({ request }) => {
    const endpoints = [
      "/health",
      `/api/monitor/pulse?simulated_date=${today}`,
      "/api/monitor/completed",
      "/api/monitor/clients",
      `/api/monitor/digest?simulated_date=${today}`,
      `/api/monitor/alerts?simulated_date=${today}&days=90`,
      "/api/ingest/documents",
    ];

    for (const endpoint of endpoints) {
      const response = await request.get(`${apiBase}${endpoint}`);
      expect(response.ok(), `${endpoint} returned ${response.status()}`).toBeTruthy();
    }
  });
});
