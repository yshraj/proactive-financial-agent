import { expect, type Locator, type Page } from "@playwright/test";

export class AiCopilotPage {
  constructor(private readonly page: Page) {}

  get input(): Locator {
    return this.page.getByTestId("ai-copilot-input");
  }

  get submitButton(): Locator {
    return this.page.getByTestId("ai-copilot-submit");
  }

  /** The most recent answer card (only the last turn carries the test id). */
  get lastAnswer(): Locator {
    return this.page.getByTestId("ai-copilot-answer");
  }

  async goto() {
    await this.page.goto("/chat");
  }

  async expectLoaded() {
    await expect(this.page.getByRole("heading", { level: 1, name: "AI Copilot" })).toBeVisible();
    await expect(this.page.getByTestId("ai-copilot-page")).toBeVisible();
  }

  /** Ask a free-text question and wait for the answer. */
  async ask(question: string) {
    // Runs are async (202 + polling), so a previous turn's answer card is
    // still visible when the POST resolves — wait for the count to grow.
    const before = await this.answerCount();
    const accepted = this.page.waitForResponse(
      (r) => r.url().includes("/api/agent/runs") && r.request().method() === "POST"
    );
    await this.input.fill(question);
    await this.submitButton.click();
    await accepted;
    await expect(this.page.getByText("Copilot answer")).toHaveCount(before + 1, {
      timeout: 15_000,
    });
    await expect(this.lastAnswer).toBeVisible();
  }

  /** Count the rendered Q&A turns (each answer card carries an AI badge). */
  async answerCount(): Promise<number> {
    return this.page.getByText("Copilot answer").count();
  }

  /** The user-side message bubble containing exactly this text. */
  userBubble(text: string): Locator {
    return this.page.getByText(text, { exact: true });
  }

  /** Stored conversation id from localStorage (null when no thread saved). */
  async storedConversationId(): Promise<string | null> {
    return this.page.evaluate(() =>
      window.localStorage.getItem("kritifin.chat.conversationId")
    );
  }
}
