import { test, expect } from "./fixtures/base";

test.describe("authentication", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("login page renders correctly", async ({ app }) => {
    await app.login.goto("/dashboard");
    await app.login.expectLoaded();
  });

  test("user can sign in", async ({ app, page }) => {
    await app.login.goto("/dashboard");
    await app.login.signIn();
    await expect(page).toHaveURL(/\/dashboard/);
    await app.dashboard.expectLoaded();
  });
});
