import { expect, type Page } from "@playwright/test";

const NAV_TEST_IDS: Record<string, string> = {
  Dashboard: "nav-link-dashboard",
  Clients: "nav-link-clients",
  "AI Copilot": "nav-link-ai-copilot",
  "Meeting Brief": "nav-link-meeting-brief",
  Alerts: "nav-link-alerts",
  Ingestion: "nav-link-ingestion",
  Settings: "nav-link-settings",
};

export class AppShell {
  constructor(private readonly page: Page) {}

  async navigateTo(label: keyof typeof NAV_TEST_IDS) {
    const testId = NAV_TEST_IDS[label];
    const mobileBtn = this.page.getByTestId("mobile-menu-button");

    if (await mobileBtn.isVisible().catch(() => false)) {
      await mobileBtn.click();
      const drawer = this.page.getByRole("dialog", { name: "Navigation menu" });
      await expect(drawer).toBeVisible();
      await drawer.getByTestId(testId).click();
      await this.page.waitForLoadState("domcontentloaded");
      return;
    }

    await this.page.getByTestId(testId).first().click();
    await this.page.waitForLoadState("domcontentloaded");
  }

  async signOutIfAvailable() {
    const button = this.page.getByTestId("sign-out-button");
    if (!(await button.isVisible().catch(() => false))) return false;
    await button.click();
    await expect(this.page).toHaveURL(/\/login/);
    return true;
  }
}
