import { test, expect } from "./fixtures/base";
import { generateDraftFromPreview } from "./helpers/credits";
import { delayRequests } from "./helpers/network";

/**
 * Deep AI Copilot coverage: conversation threading, markdown/citation
 * rendering, loading states, error recovery, conversation persistence, and
 * the regenerate/copy workflows on AI generations (draft email).
 *
 * The app is request/response (staged thinking card, no token streaming), so
 * "streaming" coverage asserts the in-flight UI contract instead: busy state,
 * locked controls, and a terminal answer.
 */

test.describe("AI Copilot conversation", () => {
  test("answer renders markdown, linked citations, and cited sources", async ({
    app,
    page,
  }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.ask("Which clients have unused ISA allowance?");

    const answer = app.aiCopilot.lastAnswer;
    // **bold** markdown renders as <strong>, not literal asterisks.
    await expect(answer.locator("strong", { hasText: "David & Sarah Chen" })).toBeVisible();
    await expect(answer).not.toContainText("**");

    // Inline [1] citation becomes an anchor that jumps to the source entry.
    const citation = answer.getByRole("link", { name: "1", exact: true });
    await expect(citation).toHaveAttribute("href", "#source-1");
    await expect(answer.getByText("1 source cited")).toBeVisible();

    await citation.click();
    const source = page.locator("#source-1");
    await expect(source).toBeVisible();
    await expect(source).toContainText("David & Sarah Chen");
    await expect(answer.getByText("1 document referenced")).toBeVisible();
  });

  test("in-flight question locks the composer and shows staged progress", async ({
    app,
    page,
  }) => {
    // Injected latency keeps the pending window observable; all assertions
    // below still auto-wait rather than sleeping.
    await delayRequests(page, "**/api/chat", 1_200);
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();

    await app.aiCopilot.input.fill("Which clients need a review?");
    await app.aiCopilot.submitButton.click();

    await expect(app.aiCopilot.thinkingCard).toBeVisible();
    await expect(app.aiCopilot.input).toBeDisabled();
    await expect(app.aiCopilot.submitButton).toBeDisabled();
    await expect(app.aiCopilot.submitButton).toHaveText(/Thinking…/);

    await expect(app.aiCopilot.lastAnswer).toBeVisible();
    await expect(app.aiCopilot.thinkingCard).toBeHidden();
    await expect(app.aiCopilot.input).toBeEnabled();
  });

  test("multi-turn thread reuses one conversation id across requests", async ({
    app,
    page,
  }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();

    const firstResponse = page.waitForResponse(
      (r) => r.url().endsWith("/api/chat") && r.request().method() === "POST"
    );
    await app.aiCopilot.ask("Which clients have unused ISA allowance?");
    const conversationId = (await (await firstResponse).json()).conversation_id as string;
    expect(conversationId).toBeTruthy();

    const secondRequest = page.waitForRequest(
      (r) => r.url().endsWith("/api/chat") && r.method() === "POST"
    );
    await app.aiCopilot.ask("And which of those have the most cash?");
    expect((await secondRequest).postDataJSON()).toMatchObject({
      query: "And which of those have the most cash?",
      conversation_id: conversationId,
    });

    const thirdRequest = page.waitForRequest(
      (r) => r.url().endsWith("/api/chat") && r.method() === "POST"
    );
    await app.aiCopilot.ask("Draft a plan for the top candidate");
    expect((await thirdRequest).postDataJSON()).toMatchObject({
      conversation_id: conversationId,
    });

    expect(await app.aiCopilot.answerCount()).toBe(3);
    expect(await app.aiCopilot.storedConversationId()).toBe(conversationId);
  });

  test("follow-up suggestions appear after an answer and are askable", async ({
    app,
    page,
  }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await expect(page.getByText("Suggested questions")).toBeVisible();

    await app.aiCopilot.ask("Which clients have unused ISA allowance?");
    await expect(page.getByText("Suggested follow-ups")).toBeVisible();

    const followUp = page.getByRole("button", {
      name: "Which clients have the largest unused ISA allowance?",
    });
    const answered = page.waitForResponse(
      (r) => r.url().endsWith("/api/chat") && r.request().method() === "POST"
    );
    await followUp.click();
    await answered;
    expect(await app.aiCopilot.answerCount()).toBe(2);
  });

  test("changing client scope starts a new conversation", async ({ app }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.ask("Which clients have unused ISA allowance?");
    expect(await app.aiCopilot.storedConversationId()).not.toBeNull();

    await app.aiCopilot.selectClientScope("Alan & Lynne Partridge");

    // The thread resets: empty state back, no answers, stored id cleared.
    await expect(app.aiCopilot.emptyState).toBeVisible();
    expect(await app.aiCopilot.answerCount()).toBe(0);
    expect(await app.aiCopilot.storedConversationId()).toBeNull();
  });

  test("scoped questions send the selected client id", async ({ app, page }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.selectClientScope("Alan & Lynne Partridge");

    const request = page.waitForRequest(
      (r) => r.url().endsWith("/api/chat") && r.method() === "POST"
    );
    await app.aiCopilot.askScopedQuestion();
    expect((await request).postDataJSON()).toMatchObject({ client_id: "c1" });
  });

  test("conversation history is restored after a page reload", async ({
    app,
    page,
  }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.ask("Which clients have unused ISA allowance?");
    const conversationId = await app.aiCopilot.storedConversationId();

    await page.reload();
    await app.aiCopilot.expectLoaded();

    // The thread re-renders from the persisted conversation, not a fresh chat.
    await expect(app.aiCopilot.lastAnswer).toBeVisible();
    await expect(
      app.aiCopilot.userBubble("Which clients have unused ISA allowance?")
    ).toBeVisible();
    expect(await app.aiCopilot.storedConversationId()).toBe(conversationId);
  });

  test("a second tab picks up the same conversation", async ({ app, page }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.ask("Which clients have unused ISA allowance?");

    const secondTab = await page.context().newPage();
    try {
      await secondTab.goto("/chat");
      await expect(secondTab.getByTestId("ai-copilot-answer")).toBeVisible();
      await expect(
        secondTab.getByText("Which clients have unused ISA allowance?", { exact: true })
      ).toBeVisible();
    } finally {
      await secondTab.close();
    }
  });

  test("deep link with ?q= asks automatically", async ({ app, page }) => {
    const answered = page.waitForResponse(
      (r) => r.url().endsWith("/api/chat") && r.request().method() === "POST"
    );
    await page.goto(`/chat?q=${encodeURIComponent("Summarise upcoming deadlines")}`);
    await answered;
    await expect(app.aiCopilot.lastAnswer).toBeVisible();
    await expect(
      app.aiCopilot.userBubble("Summarise upcoming deadlines")
    ).toBeVisible();
  });

  test("empty state's suggested question is a working entry point", async ({
    app,
    page,
  }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await expect(app.aiCopilot.emptyState).toBeVisible();

    const answered = page.waitForResponse(
      (r) => r.url().endsWith("/api/chat") && r.request().method() === "POST"
    );
    await page.getByRole("button", { name: /^Try:/ }).click();
    await answered;
    await expect(app.aiCopilot.lastAnswer).toBeVisible();
    await expect(app.aiCopilot.emptyState).toBeHidden();
  });

  test("question submits from the keyboard with Enter", async ({ app, page }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();

    const answered = page.waitForResponse(
      (r) => r.url().endsWith("/api/chat") && r.request().method() === "POST"
    );
    await app.aiCopilot.input.fill("Which clients have birthdays this month?");
    await app.aiCopilot.input.press("Enter");
    await answered;
    await expect(app.aiCopilot.lastAnswer).toBeVisible();
  });

  test("failed question offers retry and recovers", async ({ app, page }) => {
    let failNext = true;
    await page.route("**/api/chat", async (route) => {
      if (failNext) {
        failNext = false;
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Internal error" }),
        });
        return;
      }
      await route.fallback();
    });

    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.askExpectingFailure("Which clients need attention?");
    await app.aiCopilot.retryFromError();
    expect(await app.aiCopilot.answerCount()).toBe(1);
  });
});

test.describe("AI generation workflows", () => {
  test("draft email regenerate bypasses the cache with refresh=true", async ({
    app,
    page,
  }) => {
    await app.alerts.goto();
    await app.alerts.expectLoaded();

    const firstDraft = page.waitForRequest(
      (r) => r.url().includes("/api/monitor/draft-email") && r.method() === "POST"
    );
    await page.getByRole("button", { name: "Draft email" }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await generateDraftFromPreview(page);
    expect((await firstDraft).postDataJSON()).not.toHaveProperty("refresh");
    await expect(dialog.locator("pre")).toContainText(/Dear Alan/);

    const regenerated = page.waitForRequest(
      (r) =>
        r.url().includes("/api/monitor/draft-email") &&
        r.method() === "POST" &&
        r.postDataJSON()?.refresh === true
    );
    await dialog.getByTestId("regenerate-draft-button").click();
    await regenerated;
    await expect(dialog.locator("pre")).toContainText(/Dear Alan/);
  });

  test("copy draft email puts subject and body on the clipboard", async ({
    app,
    page,
  }, testInfo) => {
    test.skip(
      testInfo.project.name !== "chromium",
      "clipboard permission grants are only supported on Chromium"
    );
    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);

    await app.alerts.goto();
    await app.alerts.expectLoaded();
    await page.getByRole("button", { name: "Draft email" }).first().click();
    const dialog = page.getByRole("dialog");
    await generateDraftFromPreview(page);
    await expect(dialog.locator("pre")).toContainText(/Dear Alan/);

    await dialog.getByRole("button", { name: "Copy to clipboard" }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "Draft copied to clipboard" })
    ).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Copied" })).toBeVisible();

    const clipboard = await page.evaluate(() => navigator.clipboard.readText());
    expect(clipboard).toContain("Subject:");
    expect(clipboard).toContain("Dear Alan");
  });
});
