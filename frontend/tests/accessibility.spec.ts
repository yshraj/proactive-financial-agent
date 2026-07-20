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
  // Park the pointer so :hover styles (e.g. a button the test just clicked)
  // don't leak transient hover-state colors into the scan. Hover-state
  // contrast is tracked in the audit doc, not gated here.
  await page.mouse.move(0, 0);
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

  test("AI copilot with a rendered answer", async ({ app, page }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.ask("Which clients have unused ISA allowance?");
    await expectNoSeriousViolations(page);
  });

  test("meeting brief with generated content", async ({ app, page }) => {
    await app.meetingBrief.goto();
    await app.meetingBrief.expectLoaded();
    await app.meetingBrief.generateBrief();
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

test.describe("screen reader affordances", () => {
  test("chat answers announce politely via a live region", async ({ app }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await app.aiCopilot.ask("Which clients have unused ISA allowance?");
    // The answer card is a polite live region so screen readers hear new
    // answers without being interrupted mid-task.
    await expect(app.aiCopilot.lastAnswer).toHaveAttribute("aria-live", "polite");
  });

  test("chat input is labelled for assistive tech", async ({ app, page }) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();
    await expect(
      page.getByRole("textbox", { name: "Ask AI Copilot a question" })
    ).toBeVisible();
    await expect(page.getByLabel("Client scope")).toBeVisible();
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
    const skipLink = page.getByRole("link", { name: "Skip to content" });
    // Headless Firefox under parallel load sometimes hasn't given the
    // document keyboard focus when the first Tab arrives, so the press is
    // swallowed. Each attempt re-navigates (resetting tab order to the top)
    // and asserts the real contract: the FIRST Tab lands on the skip link.
    await expect(async () => {
      await app.dashboard.goto();
      await app.dashboard.expectLoaded();
      await page.bringToFront();
      await page.keyboard.press("Tab");
      await expect(skipLink).toBeFocused({ timeout: 1_000 });
    }).toPass({ timeout: 20_000 });

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
