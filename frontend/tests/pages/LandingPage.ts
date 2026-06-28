import { expect, type Page } from "@playwright/test";

export class LandingPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/");
  }

  async expectLoaded() {
    await expect(this.page.getByTestId("landing-page")).toBeVisible();
    await expect(
      this.page.getByRole("heading", {
        name: /Know who to contact\. What to review\. What to do next\./,
      })
    ).toBeVisible();
    await expect(this.page.getByTestId("landing-capabilities")).toBeVisible();
  }
}
