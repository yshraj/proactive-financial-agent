import { test, expect } from "./fixtures/base";
import { confirmCreditCostIfShown } from "./helpers/credits";
import { countRequests, delayRequests, fulfillJson } from "./helpers/network";

/**
 * Network behaviour: offline mode, slow responses, request/response contract
 * validation, and retry semantics (queries retry once automatically;
 * AI mutations never auto-retry — the user decides).
 */

test.describe("offline mode", () => {
  test("connection loss shows a connection error and recovers when back online", async ({
    app,
    page,
  }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();

    // Abort at the network layer (context.setOffline is not reliable for
    // localhost targets in Chromium, and a hung socket would just wait out
    // the client's 60s timeout — this fails the fetch the way a dropped
    // connection does, deterministically).
    await page.route("**/api/chat", (route) => route.abort("internetdisconnected"));
    await app.aiCopilot.input.fill("Which clients need a review?");
    await app.aiCopilot.submitButton.click();

    const errorState = app.aiCopilot.errorState;
    await expect(errorState).toBeVisible();
    await expect(errorState).toContainText(
      "Couldn't reach the AI service. Check your connection and that the backend is running."
    );

    // Connection restored: retry succeeds without re-typing the question.
    await page.unroute("**/api/chat");
    await app.aiCopilot.retryFromError();
    expect(await app.aiCopilot.answerCount()).toBe(1);
  });
});

test.describe("slow network", () => {
  test("slow brief generation holds a staged loading card until done", async ({
    app,
    page,
  }) => {
    await delayRequests(page, "**/api/chat/brief", 1_200);

    await app.meetingBrief.goto();
    await app.meetingBrief.expectLoaded();
    await page.getByTestId("generate-brief-button").click();
    await confirmCreditCostIfShown(page);

    // Loading contract: busy region + staged copy + locked generate button.
    await expect(page.getByText("Preparing your meeting brief")).toBeVisible();
    await expect(page.locator('[aria-busy="true"]').first()).toBeVisible();
    await expect(page.getByTestId("generate-brief-button")).toBeDisabled();

    await expect(page.getByTestId("generated-brief")).toBeVisible();
    await expect(page.getByText("Preparing your meeting brief")).toBeHidden();
  });
});

test.describe("request and response contracts", () => {
  test("chat request body carries only the documented fields", async ({
    app,
    page,
  }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();

    const request = page.waitForRequest(
      (r) => r.url().endsWith("/api/chat") && r.method() === "POST"
    );
    await app.aiCopilot.ask("Which clients have unused ISA allowance?");
    const sent = await request;

    // First turn: bare query — no client scope, no conversation to resume.
    expect(sent.postDataJSON()).toEqual({
      query: "Which clients have unused ISA allowance?",
    });
    expect(sent.headers()["content-type"]).toContain("application/json");
  });

  test("chat response contains an answer, citable sources, and a thread id", async ({
    app,
    page,
  }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();

    const response = page.waitForResponse(
      (r) => r.url().endsWith("/api/chat") && r.request().method() === "POST"
    );
    await app.aiCopilot.ask("Which clients have unused ISA allowance?");
    const body = await (await response).json();

    expect(typeof body.answer).toBe("string");
    expect(body.answer.length).toBeGreaterThan(0);
    expect(Array.isArray(body.sources)).toBe(true);
    expect(body.conversation_id).toBeTruthy();
    for (const source of body.sources) {
      expect(source).toMatchObject({
        ref: expect.any(Number),
        content: expect.any(String),
        client_name: expect.any(String),
      });
    }
  });
});

test.describe("retry semantics", () => {
  test("failed AI generation is never auto-retried", async ({ app, page }) => {
    const chatRequests = await countRequests(page, "/api/chat");
    await page.route("**/api/chat", (route) =>
      fulfillJson(route, 500, { detail: "Internal error" })
    );

    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.askExpectingFailure("Which clients need a review?");

    // One click, one request: a paid LLM call must not silently re-fire.
    expect(chatRequests()).toBe(1);
  });

  test("read queries retry once before surfacing an error", async ({
    app,
    page,
  }) => {
    let attempts = 0;
    await page.route("**/api/monitor/clients*", async (route) => {
      attempts += 1;
      await fulfillJson(route, 500, { detail: "Internal error" });
    });

    await app.clients.goto();
    await expect(
      page.getByRole("alert").filter({ hasText: /wrong|error/i }).first()
    ).toBeVisible();

    // React Query is configured with retry: 1 → exactly two attempts.
    expect(attempts).toBe(2);
  });

  test("an aborted request degrades to a retryable error, not a hang", async ({
    app,
    page,
  }) => {
    // Connection dropped mid-request (the fetch rejects, no HTTP response):
    // the UI must land in a recoverable error state, never a stuck spinner.
    await page.route("**/api/chat", (route) => route.abort("timedout"));

    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.input.fill("Which clients need a review?");
    await app.aiCopilot.submitButton.click();

    await expect(app.aiCopilot.errorState).toBeVisible();
    await expect(
      app.aiCopilot.errorState.getByRole("button", { name: "Try again" })
    ).toBeVisible();
  });
});
