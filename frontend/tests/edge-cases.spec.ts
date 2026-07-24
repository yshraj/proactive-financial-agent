import { test, expect } from "./fixtures/base";
import { countRequests, delayRequests, fulfillJson } from "./helpers/network";
import { oversizedPdfFile, pdfFile } from "./test-data/files";
import { EDGE_PROMPTS, LARGE_TRANSCRIPT, VERY_LONG_PROMPT } from "./test-data/prompts";

/**
 * Input extremes and hostile interaction patterns: unicode/emoji/RTL/special
 * characters, very long inputs, double submits, rapid clicking, oversized
 * files, and multi-file uploads. Payload assertions verify text survives the
 * round trip byte-for-byte, not just that "something rendered".
 */

test.describe("chat input extremes", () => {
  for (const prompt of EDGE_PROMPTS) {
    test(`${prompt.label} round-trips intact`, async ({ app, page }) => {
      await app.aiCopilot.goto();
      await app.aiCopilot.expectLoaded();

      const request = page.waitForRequest(
        (r) => r.url().endsWith("/api/agent/runs") && r.method() === "POST"
      );
      await app.aiCopilot.ask(prompt.text);

      // The exact string reaches the API — no mangling, truncation, or
      // double-encoding — and renders back in the user's message bubble.
      expect((await request).postDataJSON().query).toBe(prompt.text);
      await expect(app.aiCopilot.userBubble(prompt.text)).toBeVisible();
      await expect(app.aiCopilot.lastAnswer).toBeVisible();
    });
  }

  test("a very long prompt (~9.5k chars) submits and answers", async ({
    app,
    page,
  }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();

    const request = page.waitForRequest(
      (r) => r.url().endsWith("/api/agent/runs") && r.method() === "POST"
    );
    await app.aiCopilot.ask(VERY_LONG_PROMPT);
    expect((await request).postDataJSON().query).toBe(VERY_LONG_PROMPT);
    await expect(app.aiCopilot.lastAnswer).toBeVisible();
  });

  test("whitespace-only input cannot be submitted", async ({ app }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await expect(app.aiCopilot.submitButton).toBeDisabled();
    await app.aiCopilot.input.fill("   ");
    await expect(app.aiCopilot.submitButton).toBeDisabled();
  });
});

test.describe("double submit and rapid clicking", () => {
  test("double-clicking Ask sends exactly one request", async ({ app, page }) => {
    // Slow the response so a second click would land while the first request
    // is still in flight — the window where a double-submit bug would fire.
    await delayRequests(page, "**/api/agent/runs", 800);
    const chatRequests = await countRequests(page, "/api/agent/runs");

    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.input.fill("Which clients have unused ISA allowance?");
    await app.aiCopilot.submitButton.dblclick();

    await expect(app.aiCopilot.lastAnswer).toBeVisible();
    expect(await app.aiCopilot.answerCount()).toBe(1);
    expect(chatRequests()).toBe(1);
  });

  test("suggestion chips lock while a question is in flight", async ({
    app,
    page,
  }) => {
    await delayRequests(page, "**/api/agent/runs", 800);
    const chatRequests = await countRequests(page, "/api/agent/runs");

    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();

    const chips = page.getByRole("button", { name: /clients|review|ISA/i });
    await chips.first().click();

    // Every remaining chip is disabled during the request — rapid clicks
    // can't queue extra generations.
    await expect(page.getByRole("button", { name: /haven't had a review/ })).toBeDisabled();
    await expect(app.aiCopilot.lastAnswer).toBeVisible();
    expect(chatRequests()).toBe(1);
  });

  test("Enter mashed during flight does not resubmit", async ({ app, page }) => {
    await delayRequests(page, "**/api/agent/runs", 800);
    const chatRequests = await countRequests(page, "/api/agent/runs");

    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.input.fill("Summarise upcoming deadlines");
    await app.aiCopilot.input.press("Enter");
    // The input disables while pending, so repeat Enter presses go nowhere;
    // send them at the page level to prove nothing downstream listens.
    await page.keyboard.press("Enter");
    await page.keyboard.press("Enter");

    await expect(app.aiCopilot.lastAnswer).toBeVisible();
    expect(chatRequests()).toBe(1);
  });
});

test.describe("upload extremes", () => {
  test("a file over 20 MB is rejected client-side with no network call", async ({
    app,
    page,
  }) => {
    const uploadRequests = await countRequests(page, "/api/ingest/upload");

    await app.ingestion.goto();
    await app.ingestion.expectLoaded();
    await page.getByTestId("document-upload-input").setInputFiles(oversizedPdfFile());

    const row = page
      .getByTestId("upload-status-item")
      .filter({ hasText: "huge-factfind.pdf" });
    await expect(row).toContainText(
      "This file exceeds the current upload limit (20 MB). Please upload a smaller file."
    );
    expect(uploadRequests()).toBe(0);
  });

  test("a server-side 413 shows the backend's size-limit copy", async ({ app, page }) => {
    // Mirror the real backend 413 body (detail + structured envelope) — on
    // Lambda the limit is 4 MB, and this copy is what the user must see.
    const detail =
      "This file exceeds the current upload limit (4 MB). Please upload a smaller file. Larger file support is coming soon.";
    await page.route("**/api/ingest/upload-async", (route) =>
      fulfillJson(route, 413, {
        detail,
        error: { code: "upload_too_large", message: detail, retryable: false },
      })
    );

    await app.ingestion.goto();
    await app.ingestion.expectLoaded();
    await page.getByTestId("document-upload-input").setInputFiles(pdfFile("borderline.pdf"));

    const row = page
      .getByTestId("upload-status-item")
      .filter({ hasText: "borderline.pdf" });
    await expect(row).toContainText("This file exceeds the current upload limit (4 MB)");
  });

  test("three simultaneous uploads each track to completion", async ({
    app,
    page,
  }) => {
    await app.ingestion.goto();
    await app.ingestion.expectLoaded();
    await page
      .getByTestId("document-upload-input")
      .setInputFiles([pdfFile("batch-1.pdf"), pdfFile("batch-2.pdf"), pdfFile("batch-3.pdf")]);

    for (const name of ["batch-1.pdf", "batch-2.pdf", "batch-3.pdf"]) {
      const row = page.getByTestId("upload-status-item").filter({ hasText: name });
      await expect(row).toContainText(/Done/, { timeout: 20_000 });
    }
  });

  test("a very large pasted transcript ingests", async ({ app, page }) => {
    await app.ingestion.goto();
    await app.ingestion.expectLoaded();

    const accepted = page.waitForResponse(
      (r) => r.url().includes("/api/ingest/transcript") && r.ok()
    );
    await app.ingestion.ingestTranscript(LARGE_TRANSCRIPT);
    const response = await accepted;
    expect(response.status()).toBe(201);
  });
});

test.describe("browser lifecycle", () => {
  test("mid-thread refresh preserves the conversation", async ({ app, page }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.ask("Which clients have unused ISA allowance?");
    await app.aiCopilot.ask("And which of those have the most cash?");

    await page.reload();
    await app.aiCopilot.expectLoaded();

    // Both turns survive the reload via the persisted conversation.
    await expect(app.aiCopilot.lastAnswer).toBeVisible();
    await expect(
      app.aiCopilot.userBubble("Which clients have unused ISA allowance?")
    ).toBeVisible();
    await expect(
      app.aiCopilot.userBubble("And which of those have the most cash?")
    ).toBeVisible();
  });

  test("a stale stored conversation degrades to a fresh chat", async ({
    app,
    page,
  }) => {
    // Simulates "data was cleared on the server": the stored id points at a
    // conversation with no messages, so the page must forget it and offer a
    // clean slate instead of a broken restore.
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await page.evaluate(() => {
      window.localStorage.setItem("kritifin.chat.conversationId", "conv-gone-123");
    });

    await page.reload();
    await app.aiCopilot.expectLoaded();
    await expect(app.aiCopilot.emptyState).toBeVisible();
    expect(await app.aiCopilot.storedConversationId()).toBeNull();
  });
});
