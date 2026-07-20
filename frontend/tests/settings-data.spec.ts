import { test, expect } from "./fixtures/base";
import { countRequests, fulfillJson } from "./helpers/network";

/**
 * Settings and destructive data management. The clear-data and sample-data
 * endpoints are always route-fulfilled locally so these tests can never
 * mutate a real backend, whatever environment they run against.
 */

test.describe("clear all data", () => {
  test("confirm button stays disabled until DELETE is typed exactly", async ({
    app,
    page,
  }) => {
    const clearRequests = await countRequests(page, "/api/settings/clear-data");
    await page.route("**/api/settings/clear-data", (route) =>
      fulfillJson(route, 200, { ok: true, message: "All data cleared." })
    );

    await app.settings.goto();
    await app.settings.expectLoaded();
    await app.settings.openClearDataDialog();

    // The destructive action is gated behind typed confirmation.
    await expect(app.settings.clearDataConfirmButton).toBeDisabled();
    await app.settings.clearDataConfirmInput.fill("delete");
    await expect(app.settings.clearDataConfirmButton).toBeDisabled();
    await app.settings.clearDataConfirmInput.fill("DELETE");
    await expect(app.settings.clearDataConfirmButton).toBeEnabled();

    await app.settings.clearDataConfirmButton.click();

    // Success closes the dialog and confirms via toast; exactly one call.
    await expect(app.settings.clearDataDialog).toBeHidden();
    await expect(
      page.getByRole("status").filter({ hasText: "All data cleared" })
    ).toBeVisible();
    expect(clearRequests()).toBe(1);
  });

  test("cancel closes the dialog without any API call", async ({ app, page }) => {
    const clearRequests = await countRequests(page, "/api/settings/clear-data");

    await app.settings.goto();
    await app.settings.expectLoaded();
    await app.settings.openClearDataDialog();
    await app.settings.clearDataConfirmInput.fill("DELETE");
    await app.settings.clearDataDialog.getByRole("button", { name: "Cancel" }).click();

    await expect(app.settings.clearDataDialog).toBeHidden();
    expect(clearRequests()).toBe(0);
  });

  test("a failed clear keeps the dialog recoverable and reports the error", async ({
    app,
    page,
  }) => {
    await page.route("**/api/settings/clear-data", (route) =>
      fulfillJson(route, 500, { detail: "Vector store unavailable" })
    );

    await app.settings.goto();
    await app.settings.expectLoaded();
    await app.settings.openClearDataDialog();
    await app.settings.clearDataConfirmInput.fill("DELETE");
    await app.settings.clearDataConfirmButton.click();

    // Error toast interrupts (role=alert); the dialog stays open so the user
    // can retry or cancel — their typed confirmation is not lost.
    await expect(
      page.getByRole("alert").filter({ hasText: "Vector store unavailable" })
    ).toBeVisible();
    await expect(app.settings.clearDataDialog).toBeVisible();
    await expect(app.settings.clearDataConfirmInput).toHaveValue("DELETE");
  });
});

test.describe("first-run onboarding", () => {
  test("empty workspace shows onboarding and loads demo data", async ({
    app,
    page,
  }) => {
    // An empty pulse flips the dashboard into its first-run empty state.
    await page.route("**/api/monitor/pulse*", (route) =>
      fulfillJson(route, 200, {
        alerts: [],
        total: 0,
        high_risk: 0,
        deadlines: 0,
        client_count: 0,
        overdue_follow_ups: [],
      })
    );
    await page.route("**/api/settings/load-sample-data", (route) =>
      fulfillJson(route, 200, {
        loaded: true,
        message: "Loaded 4 demo clients and 6 alerts.",
        clients: 4,
        alerts: 6,
      })
    );

    await app.dashboard.goto();
    await expect(page.getByTestId("first-run-card")).toBeVisible();
    await expect(page.getByText("Welcome to KritiFin")).toBeVisible();

    await page.getByTestId("load-demo-data-button").click();
    await expect(
      page.getByRole("status").filter({ hasText: "Loaded 4 demo clients and 6 alerts." })
    ).toBeVisible();
  });
});

test.describe("AI audit log", () => {
  test("approving an entry flips it to Reviewed with a confirmation toast", async ({
    app,
    page,
  }) => {
    // The shared mock is stateless, so model the approve transition here:
    // after the POST, the audit list must reflect reviewed=true.
    let approved = false;
    const entry = {
      id: 7,
      kind: "review_note",
      timestamp: new Date().toISOString(),
      client_id: "c1",
      client_name: "Alan & Lynne Partridge",
      model: "gpt-4o-mini",
      preview: "# Client review note — Alan & Lynne Partridge …",
      ai_generated: false,
      reviewed: false,
      reviewed_at: null as string | null,
    };
    await page.route("**/api/compliance/audit?*", (route) =>
      fulfillJson(route, 200, {
        entries: [{ ...entry, reviewed: approved, reviewed_at: approved ? new Date().toISOString() : null }],
      })
    );
    await page.route("**/api/compliance/audit/7/approve", (route) => {
      approved = true;
      return fulfillJson(route, 200, { ...entry, reviewed: true, reviewed_at: new Date().toISOString() });
    });

    await app.settings.goto();
    await app.settings.expectLoaded();
    await page.getByTestId("audit-approve-7").click();

    await expect(
      page.getByRole("status").filter({ hasText: "Marked as reviewed." })
    ).toBeVisible();
    await expect(page.getByTestId("audit-reviewed-7")).toBeVisible();
    await expect(page.getByTestId("audit-approve-7")).toHaveCount(0);
  });
});

test.describe("workspace posture", () => {
  test("data-handling posture renders the due-diligence facts", async ({
    app,
    page,
  }) => {
    await app.settings.goto();
    await app.settings.expectLoaded();
    await app.settings.expectPostureVisible();

    const posture = page.getByTestId("posture-card");
    await expect(posture.getByText("Trains on client data")).toBeVisible();
    await expect(posture.getByText("Data residency")).toBeVisible();
    await expect(posture.getByText("Encryption in transit")).toBeVisible();
  });
});
