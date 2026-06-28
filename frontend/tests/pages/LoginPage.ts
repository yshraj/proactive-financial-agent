import { expect, type Page } from "@playwright/test";

export class LoginPage {
  constructor(private readonly page: Page) {}

  async goto(redirect = "/dashboard") {
    await this.page.goto(`/login?redirect=${encodeURIComponent(redirect)}`);
  }

  async expectLoaded() {
    await expect(this.page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
    await expect(this.page.getByText("KritiFin workspace")).toBeVisible();
  }

  async signIn() {
    await this.expectLoaded();

    const continueButton = this.page.getByTestId("continue-without-auth");
    if (await continueButton.isVisible().catch(() => false)) {
      await continueButton.click();
      return;
    }

    const email = process.env.E2E_EMAIL;
    const password = process.env.E2E_PASSWORD;
    if (!email || !password) {
      throw new Error(
        "Supabase auth is enabled for this target. Set E2E_EMAIL and E2E_PASSWORD in .env.test or CI."
      );
    }

    await this.page.getByTestId("login-email").fill(email);
    await this.page.getByTestId("login-password").fill(password);
    await this.page.getByTestId("login-submit").click();
  }
}
