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

  async approveFirstAuditEntry() {
    await this.page.locator('[data-testid^="audit-approve-"]').first().click();
  }

  /** Click an export button and return the resulting download's suggested filename. */
  async exportData(type: "clients" | "alerts"): Promise<string> {
    const testId = type === "clients" ? "export-clients-button" : "export-alerts-button";
    const [download] = await Promise.all([
      this.page.waitForEvent("download"),
      this.page.getByTestId(testId).click(),
    ]);
    return download.suggestedFilename();
  }
}
