import { expect, type Page } from "@playwright/test";

export class AlertsPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/alerts");
  }

  async expectLoaded() {
    await expect(this.page.getByRole("heading", { level: 1, name: "Alerts" })).toBeVisible();
    await expect(this.page.getByTestId("alerts-table-card")).toBeVisible();
  }

  async clickPrepBriefOnFirstRow() {
    const btn = this.page.getByTestId("prep-brief-a1");
    await expect(btn).toBeVisible();
    await btn.click();
  }
}
