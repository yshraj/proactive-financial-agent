import { test, expect } from "./fixtures/base";
import { confirmCreditCostIfShown } from "./helpers/credits";
import { fulfillJson } from "./helpers/network";

const costs = {
  chat: 1,
  report: 5,
  pdf_analysis: 2,
  draft_email: 2,
  digest: 2,
  review_note: 3,
  transcript_analysis: 2,
};

function summary(remaining: number, total = 50) {
  return {
    total_granted: total,
    used: total - remaining,
    remaining,
    version: 1,
    costs,
    contact: { email: "hello@example.com", request_enabled: true },
  };
}

async function mockBalance(page: import("@playwright/test").Page, remaining: number) {
  await page.route("**/api/credits", (route) =>
    fulfillJson(route, 200, summary(remaining))
  );
  await page.route("**/api/credits/", (route) =>
    fulfillJson(route, 200, summary(remaining))
  );
}

test.describe("lifetime credit visibility", () => {
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
    await expect(page.getByText("Credits do not renew automatically.")).toBeVisible();
    await expect(page.getByTestId("credit-history")).toBeVisible();
  });

  test("chat shows exact cost and post-action balance before Send", async ({
    app,
    page,
  }) => {
    await mockBalance(page, 20);
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();

    await expect(page.getByTestId("credit-cost-chat")).toHaveText(
      "AI Copilot question uses 1 credit · 19 remaining after completion"
    );
    await expect(page.getByTestId("ai-copilot-submit")).toContainText("Ask");
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
});

test.describe("hard backend-enforced credit stops", () => {
  test("zero credits blocks chat before the AI endpoint executes", async ({
    app,
    page,
  }) => {
    await mockBalance(page, 0);
    let chatRequests = 0;
    page.on("request", (request) => {
      if (request.url().endsWith("/api/chat") && request.method() === "POST") {
        chatRequests += 1;
      }
    });

    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.input.fill("Which clients need attention?");
    await app.aiCopilot.submitButton.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("You’re out of AI credits");
    await expect(dialog).toContainText("Remaining");
    await expect(dialog).toContainText("0");
    await expect(dialog).toContainText("Existing work is safe");
    await expect(dialog.getByRole("button", { name: "Request more credits" })).toBeVisible();
    expect(chatRequests).toBe(0);
  });

  test("an unaffordable report explains required and available credits", async ({
    app,
    page,
  }) => {
    await mockBalance(page, 3);
    let reportRequests = 0;
    page.on("request", (request) => {
      if (request.url().includes("/api/chat/brief") && request.method() === "POST") {
        reportRequests += 1;
      }
    });

    await app.meetingBrief.goto();
    await app.meetingBrief.expectLoaded();
    await page.getByTestId("generate-brief-button").click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("Not enough AI credits");
    await expect(dialog).toContainText("requires 5 credits, but 3 remain");
    expect(reportRequests).toBe(0);
  });

  test("server-side insufficient balance overrides a stale client balance", async ({
    app,
    page,
  }) => {
    await mockBalance(page, 20);
    await page.route("**/api/chat", (route) =>
      fulfillJson(route, 409, {
        error: "insufficient_credits",
        required: 1,
        remaining: 0,
        feature: "chat",
        contact_available: true,
      })
    );

    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.input.fill("Use the stale balance");
    await app.aiCopilot.submitButton.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("You’re out of AI credits");
    await expect(dialog).toContainText("requires 1 credit");
  });
});

test.describe("manual credit requests and history", () => {
  test("request success says review is manual and balance has not changed", async ({
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

    await app.aiCopilot.goto();
    await app.aiCopilot.input.fill("Blocked action");
    await app.aiCopilot.submitButton.click();
    await page.getByRole("dialog").getByRole("button", {
      name: "Request more credits",
    }).click();

    const requestDialog = page.getByRole("dialog");
    await requestDialog
      .getByTestId("credit-request-message")
      .fill("I need 25 credits to finish testing document analysis.");
    await requestDialog.getByTestId("credit-request-submit").click();

    await expect(
      page.getByRole("status").filter({
        hasText:
          "Request pending. The project owner will review it manually; your credit balance has not changed.",
      })
    ).toBeVisible();
    await expect(page.getByTestId("credit-badge")).toContainText("0 credits");
  });

  test("history shows charges, grants, remaining balance, and status", async ({
    app,
    page,
  }) => {
    await mockBalance(page, 45);
    await page.route("**/api/credits/history*", (route) =>
      fulfillJson(route, 200, {
        entries: [
          {
            id: "usage-1",
            created_at: "2026-07-20T16:00:00Z",
            feature: "report",
            delta: -5,
            balance_after: 45,
            status: "committed",
            description: "Meeting brief credit usage",
          },
          {
            id: "grant-1",
            created_at: "2026-07-19T16:00:00Z",
            feature: "credit_grant",
            delta: 25,
            balance_after: 50,
            status: "committed",
            description: "Credits added by project owner",
          },
        ],
        total: 2,
        limit: 10,
        offset: 0,
      })
    );

    await app.settings.goto();
    await app.settings.expectLoaded();
    const history = page.getByTestId("credit-history");
    await expect(history).toContainText("Meeting brief");
    await expect(history).toContainText("-5");
    await expect(history).toContainText("45 remaining");
    await expect(history).toContainText("Credits added by project owner");
    await expect(history).toContainText("+25");
  });
});
