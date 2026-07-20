import { expect, type Page } from "@playwright/test";
import { confirmCreditCostIfShown } from "../helpers/credits";

export class ClientsPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/clients");
  }

  async expectLoaded() {
    await expect(this.page.getByRole("heading", { level: 1, name: "Clients" })).toBeVisible();
    await expect(this.page.getByTestId("clients-list-page")).toBeVisible();
  }

  async expectAnalyticsVisible() {
    await expect(this.page.getByTestId("book-analytics")).toBeVisible();
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

  /** Select and apply a playbook by its option value. */
  async applyPlaybook(playbookId: string) {
    await this.page.getByTestId("playbook-select").selectOption(playbookId);
    await this.page.getByTestId("apply-playbook-button").click();
  }

  /** Open the review-note modal and wait for the generated note to render. */
  async openReviewNote() {
    await this.page.getByTestId("client-review-note-button").click();
    await confirmCreditCostIfShown(this.page);
    await expect(this.page.getByTestId("review-note-content")).toBeVisible();
  }

  /** Open the edit modal, change the name, and save. */
  async editClientName(newName: string) {
    await this.page.getByTestId("client-edit-button").click();
    await expect(this.page.getByTestId("edit-client-form")).toBeVisible();
    const nameInput = this.page.getByTestId("edit-full-name");
    await nameInput.fill(newName);
    await this.page.getByTestId("save-client-button").click();
    await expect(this.page.getByTestId("edit-client-form")).toHaveCount(0);
  }
}
