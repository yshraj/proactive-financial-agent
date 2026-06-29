import { expect, type Page } from "@playwright/test";

export class AiCopilotPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/chat");
  }

  async expectLoaded() {
    await expect(this.page.getByRole("heading", { level: 1, name: "AI Copilot" })).toBeVisible();
    await expect(this.page.getByTestId("ai-copilot-page")).toBeVisible();
  }

  async askSuggestedQuestion() {
    await this.page.getByRole("button", { name: /ISA allowance still available/ }).click();
    await expect(this.page.getByTestId("ai-copilot-answer")).toBeVisible();
    await expect(this.page.getByText(/unused ISA allowance/i)).toBeVisible();
  }

  async selectClientScope(clientLabel: string) {
    await this.page.getByTestId("copilot-client-filter").selectOption({ label: clientLabel });
  }

  async askScopedQuestion() {
    await this.page.getByTestId("ai-copilot-input").fill("Summarise open action items for this client");
    await this.page.getByTestId("ai-copilot-submit").click();
    await expect(this.page.getByTestId("ai-copilot-answer")).toBeVisible();
  }

  /** Ask a free-text question and wait for the answer. */
  async ask(question: string) {
    await this.page.getByTestId("ai-copilot-input").fill(question);
    await this.page.getByTestId("ai-copilot-submit").click();
    await expect(this.page.getByTestId("ai-copilot-answer")).toBeVisible();
  }

  /** Count the rendered Q&A turns (each answer card carries an AI badge). */
  async answerCount(): Promise<number> {
    return this.page.getByText("Copilot answer").count();
  }
}
