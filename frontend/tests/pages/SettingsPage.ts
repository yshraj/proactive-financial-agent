import { expect, type Locator, type Page } from "@playwright/test";

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

  get clearDataDialog(): Locator {
    return this.page.getByRole("dialog").filter({ hasText: "Clear all data?" });
  }

  get clearDataConfirmInput(): Locator {
    return this.clearDataDialog.getByLabel("Type DELETE to confirm");
  }

  get clearDataConfirmButton(): Locator {
    return this.clearDataDialog.getByRole("button", { name: "Clear all data" });
  }

  async openClearDataDialog() {
    await this.page.getByRole("button", { name: "Clear all data" }).click();
    await expect(this.clearDataDialog).toBeVisible();
  }
}
