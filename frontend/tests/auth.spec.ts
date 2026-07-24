import { test, expect } from "./fixtures/base";
import { fulfillJson } from "./helpers/network";

/**
 * Authentication and session flows. The local mock environment runs with
 * Supabase unconfigured (demo mode), where the auth pages render their
 * demo-workspace variants; credential-based journeys run only against
 * deployed targets that set E2E_EMAIL/E2E_PASSWORD.
 */

const supabaseCredentialsAvailable = !!process.env.E2E_EMAIL && !!process.env.E2E_PASSWORD;

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

  test("login preserves the requested destination", async ({ app, page }) => {
    await app.login.goto("/clients");
    await app.login.signIn();
    await expect(page).toHaveURL(/\/clients/);
    await app.clients.expectLoaded();
  });

  test("external redirect targets are rejected (open-redirect guard)", async ({
    page,
  }) => {
    for (const malicious of ["https://evil.example.com", "//evil.example.com"]) {
      // Firefox can abort a goto (NS_BINDING_ABORTED) when it interrupts the
      // previous page's in-flight work; re-navigating is always safe here.
      await expect(async () => {
        await page.goto(`/login?redirect=${encodeURIComponent(malicious)}`);
      }).toPass({ timeout: 15_000 });
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

  test("signup page offers a working path into the app", async ({ page }) => {
    await page.goto("/signup?redirect=/dashboard");
    await expect(
      page.getByRole("heading", { name: "Create your account" })
    ).toBeVisible();

    // Demo mode renders the continue path; configured mode renders the form.
    const continueButton = page.getByTestId("continue-without-auth");
    if (await continueButton.isVisible().catch(() => false)) {
      await continueButton.click();
      await expect(page).toHaveURL(/\/dashboard/);
    } else {
      await expect(page.getByTestId("signup-form")).toBeVisible();
      await expect(page.getByTestId("signup-email")).toBeVisible();
      await expect(page.getByTestId("signup-password")).toBeVisible();
    }
  });

  test("forgot-password page explains itself in demo mode", async ({ page }) => {
    await page.goto("/forgot-password");
    await expect(
      page.getByRole("heading", { name: "Reset your password" })
    ).toBeVisible();

    const demoNotice = page.getByText(
      "Password reset needs sign-in to be configured."
    );
    const form = page.getByTestId("forgot-form");
    // One of the two variants must render — never a blank card.
    await expect(demoNotice.or(form).first()).toBeVisible();
  });

  test("reset-password page explains itself in demo mode", async ({ page }) => {
    await page.goto("/reset-password");
    await expect(
      page.getByRole("heading", { name: "Choose a new password" })
    ).toBeVisible();
    await expect(
      page
        .getByText("Password reset needs sign-in to be configured.")
        .or(page.getByText("Verifying your reset link…"))
        .or(page.getByTestId("reset-form"))
        .first()
    ).toBeVisible();
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

  test("an expired session mid-use surfaces as an auth error, not a blank page", async ({
    app,
    page,
  }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();

    // The backend starts rejecting mid-session (token expired server-side).
    await page.route("**/api/agent/runs", (route) =>
      fulfillJson(route, 401, {
        detail: "Authentication required. Send a Supabase bearer token.",
      })
    );
    await app.aiCopilot.askExpectingFailure("Which clients need a review?");
    await expect(app.aiCopilot.errorState).toContainText(/authentication required/i);
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
