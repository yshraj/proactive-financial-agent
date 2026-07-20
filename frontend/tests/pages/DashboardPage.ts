import { expect, type Page } from "@playwright/test";

export class DashboardPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/dashboard");
  }

  async expectLoaded() {
    await expect(this.page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
    await expect(this.page.getByTestId("dashboard-hero")).toBeVisible();
  }

  async expectKpisVisible() {
    await expect(this.page.getByTestId("dashboard-kpis")).toBeVisible();
    await expect(this.page.getByTestId("kpi-card-reviews-due")).toBeVisible();
    await expect(this.page.getByTestId("kpi-card-follow-ups")).toBeVisible();
    await expect(this.page.getByTestId("kpi-card-compliance-items")).toBeVisible();
  }

  async expectDigestVisible() {
    await expect(this.page.getByTestId("dashboard-digest-card")).toBeVisible();
    await expect(this.page.getByText(/Today's briefing/i)).toBeVisible();
    const content = this.page.getByTestId("digest-content-text");
    if (!(await content.isVisible().catch(() => false))) {
      await this.page.getByTestId("generate-digest-button").click();
      await expect(content).toBeVisible();
    }
  }

  async clickFirstPrepareBrief() {
    const btn = this.page.getByTestId("prepare-brief-a1");
    await expect(btn).toBeVisible();
    await btn.click();
  }
}
