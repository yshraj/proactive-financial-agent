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
    await page.route("**/api/agent/runs", (route) => route.abort("internetdisconnected"));
    await app.aiCopilot.input.fill("Which clients need a review?");
    await app.aiCopilot.submitButton.click();

    const errorState = app.aiCopilot.errorState;
    await expect(errorState).toBeVisible();
    await expect(errorState).toContainText(
      "Couldn't reach the AI service. Check your connection and that the backend is running."
    );

    // Connection restored: retry succeeds without re-typing the question.
    await page.unroute("**/api/agent/runs");
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
  test("run creation body carries only the documented fields", async ({
    app,
    page,
  }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();

    const request = page.waitForRequest(
      (r) => r.url().endsWith("/api/agent/runs") && r.method() === "POST"
    );
    await app.aiCopilot.ask("Which clients have unused ISA allowance?");
    const sent = await request;

    // First turn: kind + bare query — no client scope, no thread to resume.
    expect(sent.postDataJSON()).toEqual({
      kind: "copilot",
      query: "Which clients have unused ISA allowance?",
    });
    expect(sent.headers()["content-type"]).toContain("application/json");
  });

  test("a finished run carries the answer, citable sources, and a thread id", async ({
    app,
    page,
  }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();

    const created = page.waitForResponse(
      (r) => r.url().endsWith("/api/agent/runs") && r.request().method() === "POST"
    );
    const finished = page.waitForResponse(async (r) => {
      if (r.request().method() !== "GET" || !/\/api\/agent\/runs\/[^/]+$/.test(r.url())) {
        return false;
      }
      try {
        return (await r.json()).status === "DONE";
      } catch {
        return false;
      }
    });
    await app.aiCopilot.ask("Which clients have unused ISA allowance?");

    const createdBody = await (await created).json();
    expect(createdBody.run_id).toBeTruthy();
    expect(createdBody.conversation_id).toBeTruthy();

    const runBody = await (await finished).json();
    expect(runBody.status).toBe("DONE");
    expect(typeof runBody.output.answer).toBe("string");
    expect(runBody.output.answer.length).toBeGreaterThan(0);
    expect(Array.isArray(runBody.output.sources)).toBe(true);
    expect(Array.isArray(runBody.steps)).toBe(true);
    expect(runBody.steps.length).toBeGreaterThan(0);
    for (const source of runBody.output.sources) {
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
    const chatRequests = await countRequests(page, "/api/agent/runs");
    await page.route("**/api/agent/runs", (route) =>
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
    await page.route("**/api/agent/runs", (route) => route.abort("timedout"));

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
