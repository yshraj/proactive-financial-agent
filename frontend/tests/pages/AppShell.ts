import { expect, type Page } from "@playwright/test";

const NAV_TEST_IDS: Record<string, string> = {
  Dashboard: "nav-link-dashboard",
  "AI Copilot": "nav-link-ai-copilot",
  "Meeting Brief": "nav-link-meeting-brief",
  Alerts: "nav-link-alerts",
  Ingestion: "nav-link-ingestion",
  Settings: "nav-link-settings",
};

export class AppShell {
  constructor(private readonly page: Page) {}

  async expectHeading(name: string) {
    await expect(this.page.getByRole("heading", { level: 1, name })).toBeVisible();
  }

  async navigateTo(label: keyof typeof NAV_TEST_IDS) {
    const links = this.page.getByTestId(NAV_TEST_IDS[label]);
    if (await links.first().isVisible().catch(() => false)) {
      await links.first().click();
      return;
    }

    if (await this.page.getByTestId("mobile-menu-button").isVisible().catch(() => false)) {
      await this.page.getByTestId("mobile-menu-button").click();
      await links.last().click();
      return;
    }

    await links.first().click();
  }

  async signOutIfAvailable() {
    const button = this.page.getByTestId("sign-out-button");
    if (!(await button.isVisible().catch(() => false))) return false;
    await button.click();
    await expect(this.page).toHaveURL(/\/login/);
    return true;
  }
}
