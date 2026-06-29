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
      "/api/monitor/analytics",
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

  test("async upload returns a job id, and job status is queryable", async ({ request }) => {
    const upload = await request.post(`${apiBase}/api/ingest/upload-async`, {
      multipart: {
        file: { name: "sample.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 test") },
      },
    });
    expect(upload.status()).toBe(202);
    const { job_id } = await upload.json();
    expect(job_id).toBeTruthy();

    const status = await request.get(`${apiBase}/api/ingest/jobs/${job_id}`);
    expect(status.ok()).toBeTruthy();
    const job = await status.json();
    expect(["PENDING", "PROCESSING", "DONE", "ERROR"]).toContain(job.status);
  });

  test("playbooks list and apply", async ({ request }) => {
    const list = await request.get(`${apiBase}/api/monitor/playbooks`);
    expect(list.ok()).toBeTruthy();
    expect((await list.json()).playbooks.length).toBeGreaterThan(0);

    const applied = await request.post(`${apiBase}/api/monitor/clients/c1/apply-playbook`, {
      data: { playbook_id: "annual_review" },
    });
    expect(applied.ok()).toBeTruthy();
    expect((await applied.json()).applied).toBeGreaterThan(0);
  });

  test("compliance scan and audit log endpoints respond", async ({ request }) => {
    const scan = await request.post(`${apiBase}/api/compliance/scan`, {
      data: { text: "Client mentioned a cancer diagnosis and unclear fees." },
    });
    expect(scan.ok()).toBeTruthy();
    const audit = await request.get(`${apiBase}/api/compliance/audit`);
    expect(audit.ok()).toBeTruthy();
    expect(Array.isArray((await audit.json()).entries)).toBeTruthy();
  });
});
