import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "./fixtures/base";

/**
 * Automated WCAG scans (axe-core) on the key surfaces. Gate on serious and
 * critical violations; moderate/minor findings are reported in the audit doc
 * and fixed opportunistically, so this suite stays actionable rather than
 * aspirational.
 */

const GATED_IMPACTS = new Set(["serious", "critical"]);

async function expectNoSeriousViolations(page: import("@playwright/test").Page) {
  // Let entrance animations (framer-motion) settle so transient mid-fade
  // opacity doesn't produce spurious contrast findings.
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(400);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const gated = results.violations.filter((v) => GATED_IMPACTS.has(v.impact ?? ""));
  expect(
    gated,
    gated
      .map(
        (v) =>
          `${v.impact}: ${v.id} — ${v.help}\n` +
          v.nodes.slice(0, 3).map((n) => `    ${n.target.join(" ")}`).join("\n")
      )
      .join("\n\n")
  ).toEqual([]);
}

test.describe("accessibility scans", () => {
  test("landing page", async ({ app, page }) => {
    await app.landing.goto();
    await expectNoSeriousViolations(page);
  });

  test("login page", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expectNoSeriousViolations(page);
  });

  test("dashboard", async ({ app, page }) => {
    await app.dashboard.goto();
    await app.dashboard.expectLoaded();
    await expectNoSeriousViolations(page);
  });

  test("clients list", async ({ app, page }) => {
    await app.clients.goto();
    await app.clients.expectLoaded();
    await expectNoSeriousViolations(page);
  });

  test("ingestion", async ({ app, page }) => {
    await app.ingestion.goto();
    await app.ingestion.expectLoaded();
    await expectNoSeriousViolations(page);
  });

  test("settings", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByTestId("settings-page")).toBeVisible();
    await expectNoSeriousViolations(page);
  });

  test("404 page", async ({ page }) => {
    await page.goto("/missing-route");
    await expect(page.getByText("Error 404")).toBeVisible();
    await expectNoSeriousViolations(page);
  });
});

const isTouchProject = (name: string) =>
  name.includes("mobile") || name.includes("tablet");

// Physical-keyboard behaviour only applies to pointer+keyboard (desktop)
// projects; touch device emulation has no Tab focus model.
test.describe("keyboard navigation", () => {
  test("skip link jumps to main content", async ({ app, page }, testInfo) => {
    // WebKit only Tabs through form controls unless macOS "Full Keyboard
    // Access" is enabled, so links aren't reachable via Tab in automation.
    test.skip(
      isTouchProject(testInfo.project.name) || testInfo.project.name === "webkit",
      "requires a desktop keyboard focus model (not WebKit/touch)"
    );
    await app.dashboard.goto();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/#main-content/);
  });
});

test.describe("mobile drawer", () => {
  test("traps and restores focus", async ({ app, page }, testInfo) => {
    test.skip(
      !testInfo.project.name.includes("mobile"),
      "the drawer only renders below the md breakpoint"
    );
    await app.dashboard.goto();
    await page.getByTestId("mobile-menu-button").click();
    const drawer = page.getByRole("dialog", { name: "Navigation menu" });
    await expect(drawer).toBeVisible();
    // Focus lands inside the drawer on open.
    await expect(drawer.locator(":scope *:focus")).toHaveCount(1);
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();
    await expect(page.getByTestId("mobile-menu-button")).toBeFocused();
  });
});
