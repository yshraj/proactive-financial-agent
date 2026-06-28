import { expect, type Page } from "@playwright/test";

export class MeetingBriefPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/brief");
  }

  async expectLoaded() {
    await expect(this.page.getByRole("heading", { level: 1, name: "Meeting Brief" })).toBeVisible();
    await expect(this.page.getByTestId("meeting-brief-page")).toBeVisible();
  }

  async generateBrief() {
    await this.page.getByTestId("generate-brief-button").click();
    await expect(this.page.getByTestId("generated-brief")).toBeVisible();
  }
}
