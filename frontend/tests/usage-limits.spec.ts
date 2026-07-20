import { test, expect } from "./fixtures/base";
import {
  confirmCreditCostIfShown,
  generateDraftFromPreview,
} from "./helpers/credits";
import {
  RATE_LIMIT_DETAIL,
  fulfillRateLimited,
  rateLimitFirst,
  rateLimitResponse,
} from "./helpers/network";
import { pdfFile } from "./test-data/files";

/**
 * Temporary burst limits. Lifetime credits are tested separately in
 * credits.spec.ts; slowapi answers with a structured 429:
 * {error: "rate_limit", limit_type: request,
 * reset_at, detail} plus Retry-After / X-RateLimit-* headers. These tests
 * inject that exact shape per-surface and assert that every blocked action
 * shows the correct message, never crashes the page, preserves user input,
 * and recovers once the limit clears.
 */

test.describe("AI endpoint burst protection", () => {
  test("blocked chat shows the burst-limit message and recovers on retry", async ({
    app,
    page,
  }) => {
    const counter = await rateLimitFirst(page, "**/api/chat", "request", 1);

    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.askExpectingFailure("Which clients need a review?");

    // The backend's human-readable detail is surfaced verbatim — the user
    // learns this is a temporary request burst, not exhausted credits.
    await expect(app.aiCopilot.errorState).toContainText(RATE_LIMIT_DETAIL);

    // Blocked requests must not be silently retried: one request, one block.
    expect(counter.blocked()).toBe(1);
    expect(counter.total()).toBe(1);

    // The composer survives the block — input is editable again for retry.
    await expect(app.aiCopilot.input).toBeEnabled();

    // The short request window clears: the next attempt goes through.
    await app.aiCopilot.retryFromError();
    expect(counter.total()).toBe(2);
    expect(counter.blocked()).toBe(1);
  });

  test("429 without a detail body falls back to friendly rate-limit copy", async ({
    app,
    page,
  }) => {
    await page.route("**/api/chat", (route) =>
      fulfillRateLimited(route, "request", { detail: null })
    );

    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.askExpectingFailure("Which clients need a review?");

    await expect(app.aiCopilot.errorState).toContainText(
      "Too many AI requests in a short period. Please wait a moment and try again."
    );
  });

  test("429 responses carry Retry-After and X-RateLimit headers for clients", async ({
    app,
    page,
  }) => {
    await page.route("**/api/chat", (route) =>
      fulfillRateLimited(route, "request", { retryAfterSeconds: 120 })
    );

    const blocked = page.waitForResponse(
      (r) => r.url().endsWith("/api/chat") && r.status() === 429
    );
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.askExpectingFailure("Which clients need a review?");

    const response = await blocked;
    expect(response.headers()["retry-after"]).toBe("120");
    expect(response.headers()["x-ratelimit-remaining"]).toBe("0");
    const body = await response.json();
    expect(body).toMatchObject({ error: "rate_limit", limit_type: "request" });
    expect(new Date(body.reset_at).getTime()).toBeGreaterThan(Date.now());
  });

  test("blocked meeting brief generation shows burst-limit copy and retries", async ({
    app,
    page,
  }) => {
    const counter = await rateLimitFirst(page, "**/api/chat/brief", "request", 1);

    await app.meetingBrief.goto();
    await app.meetingBrief.expectLoaded();

    const blocked = page.waitForResponse(
      (r) => r.url().includes("/api/chat/brief") && r.status() === 429
    );
    await page.getByTestId("generate-brief-button").click();
    await confirmCreditCostIfShown(page);
    await blocked;

    const errorState = page
      .getByRole("alert")
      .filter({ hasText: "Couldn't generate the brief" });
    await expect(errorState).toBeVisible();
    await expect(errorState).toContainText(RATE_LIMIT_DETAIL);

    await errorState.getByRole("button", { name: "Try again" }).click();
    await confirmCreditCostIfShown(page);
    await expect(page.getByTestId("generated-brief")).toBeVisible();
    expect(counter.total()).toBe(2);
  });

  test("blocked draft email inside the modal shows burst-limit copy and retries", async ({
    app,
    page,
  }) => {
    const counter = await rateLimitFirst(
      page,
      "**/api/monitor/draft-email",
      "request",
      1
    );

    await app.alerts.goto();
    await app.alerts.expectLoaded();
    await page.getByRole("button", { name: "Draft email" }).first().click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await generateDraftFromPreview(page);
    const errorState = dialog
      .getByRole("alert")
      .filter({ hasText: "Couldn't generate the draft" });
    await expect(errorState).toBeVisible();
    await expect(errorState).toContainText(RATE_LIMIT_DETAIL);

    await errorState.getByRole("button", { name: "Try again" }).click();
    await expect(dialog.locator("pre")).toContainText(/Dear Alan/);
    expect(counter.total()).toBe(2);
  });

  test("blocked review note never exposes a copy action for missing content", async ({
    app,
    page,
  }) => {
    // The credit confirmation happens before the note request; a blocked
    // backend response then becomes a recoverable modal error.
    await page.route("**/review-note", (route) =>
      fulfillRateLimited(route, "request")
    );

    await page.goto("/clients/c1");
    await app.clients.expectDetailLoaded();

    const blocked = page.waitForResponse(
      (r) => r.url().includes("/review-note") && r.status() === 429
    );
    await page.getByTestId("client-review-note-button").click();
    await confirmCreditCostIfShown(page);
    await blocked;

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByTestId("copy-review-note")).toBeDisabled();
    await expect(dialog.getByTestId("review-note-content")).toHaveCount(0);
    await expect(dialog.getByRole("alert")).toContainText(RATE_LIMIT_DETAIL);

    // The user can always close out of the blocked state. (exact: the modal
    // also has an icon button named "Close dialog".)
    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    await expect(dialog).toBeHidden();
  });
});

test.describe("ingestion endpoint burst protection", () => {
  test("blocked upload marks the row as failed without losing the queue UI", async ({
    app,
    page,
  }) => {
    await page.route("**/api/ingest/upload-async", (route) =>
      fulfillRateLimited(route, "request")
    );

    await app.ingestion.goto();
    await app.ingestion.expectLoaded();
    await page.getByTestId("document-upload-input").setInputFiles(pdfFile("burst-blocked.pdf"));

    const row = page
      .getByTestId("upload-status-item")
      .filter({ hasText: "burst-blocked.pdf" });
    await expect(row).toContainText(RATE_LIMIT_DETAIL);

    // The page stays functional: stored documents are still listed.
    await expect(page.getByTestId("stored-documents")).toBeVisible();
  });

  test("blocked transcript ingestion surfaces the burst-limit message", async ({
    app,
    page,
  }) => {
    await page.route("**/api/ingest/transcript", (route) =>
      fulfillRateLimited(route, "request")
    );

    await app.ingestion.goto();
    await app.ingestion.expectLoaded();

    const blocked = page.waitForResponse(
      (r) => r.url().includes("/api/ingest/transcript") && r.status() === 429
    );
    await app.ingestion.ingestTranscript(
      "Met with the client to review pensions and agreed a follow-up on protection cover."
    );
    await blocked;

    // Ingestion failures notify via an error toast (role=alert).
    await expect(
      page.getByRole("alert").filter({ hasText: RATE_LIMIT_DETAIL })
    ).toBeVisible();
    // The pasted transcript is not lost on failure.
    await expect(page.getByTestId("transcript-input")).toHaveValue(/review pensions/);
  });
});

test.describe("per-minute burst limit (limit_type=request)", () => {
  test("rate-limited dashboard degrades to an error state and recovers", async ({
    app,
    page,
  }) => {
    // Queries retry once, so block the first two attempts to surface the
    // error state, then let the retry affordance succeed.
    const counter = await rateLimitFirst(page, "**/api/monitor/pulse*", "request", 2);

    await app.dashboard.goto();
    const errorState = page
      .getByRole("alert")
      .filter({ hasText: "Couldn't load your dashboard" });
    await expect(errorState).toBeVisible();
    await expect(errorState).toContainText(RATE_LIMIT_DETAIL);

    await errorState.getByRole("button", { name: "Try again" }).click();
    await app.dashboard.expectLoaded();
    expect(counter.blocked()).toBe(2);
  });

  test("every request carries the session id used for burst protection", async ({
    app,
    page,
  }) => {
    const chatRequest = page.waitForRequest(
      (r) => r.url().endsWith("/api/chat") && r.method() === "POST"
    );
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.ask("Which clients have unused ISA allowance?");

    // X-Session-Id scopes demo-mode limits per browser; without it every
    // visitor would drain one shared bucket.
    const sessionId = (await chatRequest).headers()["x-session-id"];
    expect(sessionId).toBeTruthy();

    const briefRequest = page.waitForRequest(
      (r) => r.url().includes("/api/chat/brief") && r.method() === "POST"
    );
    await app.meetingBrief.goto();
    await app.meetingBrief.generateBrief();
    // The same stable id is sent on every AI surface.
    expect((await briefRequest).headers()["x-session-id"]).toBe(sessionId);
  });

  test("a mid-conversation block keeps earlier answers on screen", async ({
    app,
    page,
  }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.ask("Which clients have unused ISA allowance?");

    await page.route("**/api/chat", (route) => fulfillRateLimited(route, "request"));
    await app.aiCopilot.askExpectingFailure("And who has the most cash?");

    // The first turn is intact; only the new question failed.
    expect(await app.aiCopilot.answerCount()).toBe(1);
    await expect(app.aiCopilot.errorState).toContainText(RATE_LIMIT_DETAIL);
  });
});

test.describe("rate limit response contract", () => {
  test("the mocked shape matches the backend handler field-for-field", () => {
    // Guard the helper itself: if the backend contract changes shape, update
    // helpers/network.ts consciously rather than letting specs drift.
    const { status, headers, body } = rateLimitResponse("request", {
      retryAfterSeconds: 30,
    });
    expect(status).toBe(429);
    expect(headers["Retry-After"]).toBe("30");
    const parsed = JSON.parse(body);
    expect(Object.keys(parsed).sort()).toEqual([
      "detail",
      "error",
      "limit_type",
      "reset_at",
    ]);
    expect(parsed.error).toBe("rate_limit");
    expect(parsed.limit_type).toBe("request");
  });
});
