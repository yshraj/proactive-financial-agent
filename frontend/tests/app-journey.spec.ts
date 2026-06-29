import { test, expect } from "./fixtures/base";
import { waitForSuccessfulApiResponse } from "./helpers/api";
import { captureMajorPageScreenshot } from "./helpers/screenshots";

test.describe("complete adviser journey", () => {
  test("dashboard loads, KPIs are visible, and core API requests succeed", async ({ app, page }, testInfo) => {
    await waitForSuccessfulApiResponse(page, "/api/monitor/pulse", () => app.dashboard.goto());
    await app.dashboard.expectLoaded();
    await app.dashboard.expectKpisVisible();
    await captureMajorPageScreenshot(page, testInfo, "dashboard");
  });

  test("navigation between all protected pages works without console errors", async ({ app, page }, testInfo) => {
    await app.dashboard.goto();
    await app.dashboard.expectLoaded();

    await app.shell.navigateTo("AI Copilot");
    await app.aiCopilot.expectLoaded();
    await captureMajorPageScreenshot(page, testInfo, "ai-copilot");

    await app.shell.navigateTo("Clients");
    await app.clients.expectLoaded();
    await captureMajorPageScreenshot(page, testInfo, "clients");

    await app.shell.navigateTo("Meeting Brief");
    await app.meetingBrief.expectLoaded();
    await captureMajorPageScreenshot(page, testInfo, "meeting-brief");

    await app.shell.navigateTo("Ingestion");
    await app.ingestion.expectLoaded();
    await captureMajorPageScreenshot(page, testInfo, "ingestion");

    await app.shell.navigateTo("Alerts");
    await app.shell.expectHeading("Alerts");
    await expect(page.getByTestId("alerts-table-card")).toBeVisible();

    await app.shell.navigateTo("Settings");
    await app.settings.expectLoaded();
    await captureMajorPageScreenshot(page, testInfo, "settings");

    await app.shell.navigateTo("Dashboard");
    await app.dashboard.expectLoaded();
  });

  test("AI Copilot and Meeting Brief complete their main workflows", async ({ app }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.askSuggestedQuestion();

    await app.meetingBrief.goto();
    await app.meetingBrief.expectLoaded();
    await app.meetingBrief.generateBrief();
  });

  test("document upload starts processing", async ({ app, page }) => {
    await waitForSuccessfulApiResponse(page, "/api/ingest/documents", () => app.ingestion.goto());
    await app.ingestion.expectLoaded();
    await waitForSuccessfulApiResponse(page, "/api/ingest/upload", () => app.ingestion.uploadSampleDocument());
  });

  test("paste transcript ingestion", async ({ app, page }) => {
    await app.ingestion.goto();
    await app.ingestion.expectLoaded();
    await waitForSuccessfulApiResponse(page, "/api/ingest/transcript", () =>
      app.ingestion.ingestTranscript(
        "Met with the client today. They confirmed their pension contribution increase and we agreed to review protection cover before the next annual review."
      )
    );
  });

  test("compliance scan flags vulnerability and consumer duty signals", async ({ app, page }) => {
    await app.ingestion.goto();
    await app.ingestion.expectLoaded();
    await app.ingestion.runComplianceScan(
      "Client disclosed a recent cancer diagnosis and said the fees were unclear."
    );
    await expect(page.getByTestId("compliance-scan-results")).toContainText("Health");
    await expect(page.getByTestId("compliance-scan-results")).toContainText("Consumer understanding");
  });

  test("settings page exports clients and alerts as CSV", async ({ app }) => {
    await app.settings.goto();
    await app.settings.expectLoaded();
    expect(await app.settings.exportData("clients")).toBe("kritifin-clients.csv");
    expect(await app.settings.exportData("alerts")).toBe("kritifin-alerts.csv");
  });

  test("settings page loads and logout works when auth is enabled", async ({ app }) => {
    await app.settings.goto();
    await app.settings.expectLoaded();
    const signedOut = await app.shell.signOutIfAvailable();
    test.skip(!signedOut, "Auth is not configured in this environment, so there is no session to sign out.");
  });
});
