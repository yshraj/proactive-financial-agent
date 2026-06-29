import { expect, type Page } from "@playwright/test";

export class ClientsPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/clients");
  }

  async expectLoaded() {
    await expect(this.page.getByRole("heading", { level: 1, name: "Clients" })).toBeVisible();
    await expect(this.page.getByTestId("clients-list-page")).toBeVisible();
  }

  async openFirstClient() {
    const link = this.page.getByTestId("client-link-c1");
    await expect(link).toBeVisible();
    await link.click();
    await expect(this.page.getByTestId("client-detail-page")).toBeVisible();
  }

  async expectDetailLoaded() {
    await expect(this.page.getByTestId("client-detail-page")).toBeVisible();
    await expect(this.page.getByTestId("client-ai-summary")).toBeVisible();
  }
}
