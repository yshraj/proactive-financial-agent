import { expect, type Page } from "@playwright/test";

export class SettingsPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/settings");
  }

  async expectLoaded() {
    await expect(this.page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
    await expect(this.page.getByTestId("settings-page")).toBeVisible();
    await expect(this.page.getByText("Data & privacy")).toBeVisible();
  }

  async expectAuditLogVisible() {
    await expect(this.page.getByTestId("audit-log-card")).toBeVisible();
  }

  async expectPostureVisible() {
    await expect(this.page.getByTestId("posture-card")).toBeVisible();
  }
}
