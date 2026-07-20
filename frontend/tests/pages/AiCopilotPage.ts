import { expect, type Locator, type Page } from "@playwright/test";

export class AiCopilotPage {
  constructor(private readonly page: Page) {}

  get input(): Locator {
    return this.page.getByTestId("ai-copilot-input");
  }

  get submitButton(): Locator {
    return this.page.getByTestId("ai-copilot-submit");
  }

  get clientScope(): Locator {
    return this.page.getByTestId("copilot-client-filter");
  }

  /** The most recent answer card (only the last turn carries the test id). */
  get lastAnswer(): Locator {
    return this.page.getByTestId("ai-copilot-answer");
  }

  /** ErrorState rendered when the chat mutation fails. */
  get errorState(): Locator {
    return this.page
      .getByRole("alert")
      .filter({ hasText: "Couldn't get an answer" });
  }

  /** Staged loading card shown while the request is in flight. */
  get thinkingCard(): Locator {
    return this.page.getByText("AI Copilot is thinking");
  }

  get emptyState(): Locator {
    return this.page.getByText("Ask your first question");
  }

  async goto() {
    await this.page.goto("/chat");
  }

  async expectLoaded() {
    await expect(this.page.getByRole("heading", { level: 1, name: "AI Copilot" })).toBeVisible();
    await expect(this.page.getByTestId("ai-copilot-page")).toBeVisible();
  }

  async askSuggestedQuestion() {
    // Wait on the chat response itself, not just the DOM: under parallel load
    // (esp. Firefox) the answer render lags the click, which flaked when we
    // only waited on visibility.
    const answered = this.page.waitForResponse(
      (r) => r.url().includes("/api/chat") && r.request().method() === "POST"
    );
    await this.page.getByRole("button", { name: /ISA allowance still available/ }).click();
    await answered;
    const answer = this.page.getByTestId("ai-copilot-answer");
    await expect(answer).toBeVisible();
    // Scope to the answer card: the same phrase also appears in follow-up
    // suggestion chips, which would otherwise be a strict-mode violation.
    await expect(answer.getByText(/unused ISA allowance/i)).toBeVisible();
  }

  async selectClientScope(clientLabel: string) {
    await this.clientScope.selectOption({ label: clientLabel });
  }

  async askScopedQuestion() {
    await this.ask("Summarise open action items for this client");
  }

  /** Ask a free-text question and wait for the answer. */
  async ask(question: string) {
    const answered = this.page.waitForResponse(
      (r) => r.url().includes("/api/chat") && r.request().method() === "POST"
    );
    await this.input.fill(question);
    await this.submitButton.click();
    await answered;
    await expect(this.lastAnswer).toBeVisible();
  }

  /** Ask a question whose request is expected to fail; waits for the error UI. */
  async askExpectingFailure(question: string) {
    const failed = this.page.waitForResponse(
      (r) =>
        r.url().includes("/api/chat") &&
        r.request().method() === "POST" &&
        !r.ok()
    );
    await this.input.fill(question);
    await this.submitButton.click();
    await failed;
    await expect(this.errorState).toBeVisible();
  }

  /** Click "Try again" in the chat error state and wait for a good answer. */
  async retryFromError() {
    const answered = this.page.waitForResponse(
      (r) =>
        r.url().includes("/api/chat") &&
        r.request().method() === "POST" &&
        r.ok()
    );
    await this.errorState.getByRole("button", { name: "Try again" }).click();
    await answered;
    await expect(this.lastAnswer).toBeVisible();
    await expect(this.errorState).toBeHidden();
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
