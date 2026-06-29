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

  test("CSV export returns a downloadable text/csv body", async ({ request }) => {
    const response = await request.get(`${apiBase}/api/monitor/export?type=clients`);
    expect(response.ok()).toBeTruthy();
    expect(response.headers()["content-type"]).toContain("text/csv");
    const body = await response.text();
    expect(body.split("\r\n")[0]).toContain("Name");
  });

  test("load-sample-data reports how many records were created", async ({ request }) => {
    const response = await request.post(`${apiBase}/api/settings/load-sample-data`);
    expect(response.ok()).toBeTruthy();
    const json = await response.json();
    expect(json.loaded).toBe(true);
    expect(json.clients).toBeGreaterThan(0);
  });

  test("client edit accepts a partial profile update", async ({ request }) => {
    const response = await request.patch(`${apiBase}/api/monitor/clients/c1`, {
      data: { full_name: "Updated Name", risk_score: 4 },
    });
    expect(response.ok()).toBeTruthy();
    const json = await response.json();
    expect(json.full_name).toBe("Updated Name");
  });
});
