import { test, expect } from "./fixtures/base";
import { confirmCreditCostIfShown } from "./helpers/credits";
import { fulfillJson } from "./helpers/network";

/**
 * Lifetime AI-credit guardrails: the balance is visible everywhere, expensive
 * actions require explicit confirmation, and a zero balance blocks AI actions
 * client-side with a manual request path. Balances are route-mocked so each
 * scenario is deterministic.
 */

const costs = {
  chat: 1,
  report: 5,
  pdf_analysis: 2,
  draft_email: 2,
  digest: 2,
  review_note: 3,
  transcript_analysis: 2,
};

async function mockBalance(page: import("@playwright/test").Page, remaining: number) {
  const summary = {
    total_granted: 50,
    used: 50 - remaining,
    remaining,
    version: 1,
    costs,
    contact: { email: "hello@example.com", request_enabled: true },
  };
  await page.route("**/api/credits", (route) => fulfillJson(route, 200, summary));
  await page.route("**/api/credits/", (route) => fulfillJson(route, 200, summary));
}

test.describe("AI credits", () => {
  test("header, sidebar, and settings show one consistent balance", async ({
    app,
    page,
  }) => {
    await mockBalance(page, 45);
    await app.dashboard.goto();
    await app.dashboard.expectLoaded();

    await expect(page.getByTestId("credit-badge")).toHaveAccessibleName(
      "45 AI credits remaining"
    );
    await expect(page.getByTestId("credit-widget-compact")).toContainText("45");

    await page.getByTestId("credit-badge").click();
    await expect(page).toHaveURL(/\/settings#ai-credits/);
    await expect(page.getByTestId("credit-widget")).toContainText(
      "45 of 50 remaining"
    );
  });

  test("a five-credit report requires confirmation before any request", async ({
    app,
    page,
  }) => {
    await mockBalance(page, 18);
    let requests = 0;
    page.on("request", (request) => {
      if (request.url().includes("/api/chat/brief") && request.method() === "POST") {
        requests += 1;
      }
    });

    await app.meetingBrief.goto();
    await app.meetingBrief.expectLoaded();
    await page.getByTestId("generate-brief-button").click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("Use 5 AI credits?");
    await expect(dialog).toContainText("You will have 13 remaining");
    expect(requests).toBe(0);

    await confirmCreditCostIfShown(page);
    await expect(page.getByTestId("generated-brief")).toBeVisible();
    expect(requests).toBe(1);
  });

  test("zero credits blocks AI actions and offers a manual request", async ({
    app,
    page,
  }) => {
    await mockBalance(page, 0);
    await page.route("**/api/credits/requests", (route) =>
      fulfillJson(route, 202, {
        id: "request-1",
        status: "pending",
        message: "Pending review",
        created_at: new Date().toISOString(),
        contact_email: "hello@example.com",
      })
    );
    let chatRequests = 0;
    page.on("request", (request) => {
      if (request.url().endsWith("/api/agent/runs") && request.method() === "POST") {
        chatRequests += 1;
      }
    });

    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.input.fill("Which clients need attention?");
    await app.aiCopilot.submitButton.click();

    // The hard stop happens client-side: no AI request is ever sent.
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("You’re out of AI credits");
    expect(chatRequests).toBe(0);

    // The only way forward is a manual request, reviewed by the owner.
    await dialog.getByRole("button", { name: "Request more credits" }).click();
    const requestDialog = page.getByRole("dialog");
    await requestDialog
      .getByTestId("credit-request-message")
      .fill("I need 25 credits to finish document analysis.");
    await requestDialog.getByTestId("credit-request-submit").click();

    await expect(
      page.getByRole("status").filter({
        hasText:
          "Request pending. The project owner will review it manually; your credit balance has not changed.",
      })
    ).toBeVisible();
    await expect(page.getByTestId("credit-badge")).toContainText("0 credits");
  });
});
