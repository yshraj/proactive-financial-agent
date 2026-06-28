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
}
