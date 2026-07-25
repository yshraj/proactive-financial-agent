import { test, expect } from "./fixtures/base";

/**
 * Entry and session flows. The local mock environment runs with Supabase
 * unconfigured (demo mode); credential-based journeys run only against
 * deployed targets that set E2E_EMAIL/E2E_PASSWORD.
 */

const supabaseCredentialsAvailable = !!process.env.E2E_EMAIL && !!process.env.E2E_PASSWORD;

test.describe("entry", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("landing page loads", async ({ app }) => {
    await app.landing.goto();
    await app.landing.expectLoaded();
  });

  test("sign in lands on the requested page", async ({ app, page }) => {
    await app.login.goto("/clients");
    await app.login.expectLoaded();
    await app.login.signIn();
    await expect(page).toHaveURL(/\/clients/);
    await app.clients.expectLoaded();
  });

  test("external redirect targets are rejected (open-redirect guard)", async ({
    page,
  }) => {
    for (const malicious of ["https://evil.example.com", "//evil.example.com"]) {
      await page.goto(`/login?redirect=${encodeURIComponent(malicious)}`);
      const cta = page
        .getByTestId("continue-without-auth")
        .or(page.getByTestId("login-form"));
      await expect(cta.first()).toBeVisible();
      // Demo mode: the continue link must fall back to the internal entry
      // point, never the attacker-supplied URL.
      const continueLink = page.getByTestId("continue-without-auth");
      if (await continueLink.isVisible().catch(() => false)) {
        await expect(continueLink).toHaveAttribute("href", "/dashboard");
      }
    }
  });
});

test.describe("session behaviour", () => {
  test("stored session state opens protected pages directly", async ({
    app,
    page,
  }) => {
    // The suite reuses auth.setup's storage state: protected routes must load
    // without bouncing through /login again.
    await page.goto("/dashboard");
    await expect(page).not.toHaveURL(/\/login/);
    await app.dashboard.expectLoaded();
  });
});

test.describe("credentialed journeys (deployed targets only)", () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test.skip(
    !supabaseCredentialsAvailable,
    "requires a Supabase-enabled target with E2E_EMAIL / E2E_PASSWORD"
  );

  test("wrong password shows the provider error without leaving the page", async ({
    app,
    page,
  }) => {
    await app.login.goto("/dashboard");
    await app.login.expectLoaded();
    await page.getByTestId("login-email").fill(process.env.E2E_EMAIL!);
    await page.getByTestId("login-password").fill("definitely-wrong-password");
    await page.getByTestId("login-submit").click();

    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("sign out returns to login and drops the session", async ({ app, page }) => {
    await app.login.goto("/dashboard");
    await app.login.signIn();
    await app.dashboard.expectLoaded();

    const signedOut = await app.shell.signOutIfAvailable();
    expect(signedOut).toBe(true);
    // A protected route now redirects back to login.
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
  });
});
