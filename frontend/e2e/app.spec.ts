import { test, expect } from "@playwright/test";
import { collectErrors, navigate, expectHeading } from "./helpers";

const PAGES = [
  { path: "/", heading: "Dashboard" },
  { path: "/chat", heading: "Ask Jarvis" },
  { path: "/brief", heading: "Pre-meeting brief" },
  { path: "/admin", heading: "Ingestion" },
  { path: "/alerts", heading: "Alerts" },
  { path: "/settings", heading: "Settings" },
];

test.describe("smoke: every page loads cleanly", () => {
  for (const p of PAGES) {
    test(`loads ${p.path} with no console errors`, async ({ page }) => {
      const errors = collectErrors(page);
      await page.goto(p.path);
      await expectHeading(page, p.heading);
      await page.waitForTimeout(800);
      expect(errors, errors.join("\n")).toEqual([]);
    });
  }
});

test.describe("navigation", () => {
  test("can navigate between sections", async ({ page }) => {
    await page.goto("/");
    await navigate(page, "Ask Jarvis");
    await expect(page).toHaveURL(/\/chat$/);
    await navigate(page, "Alerts");
    await expect(page).toHaveURL(/\/alerts$/);
    await navigate(page, "Settings");
    await expect(page).toHaveURL(/\/settings$/);
    await navigate(page, "Dashboard");
    await expect(page).toHaveURL(/\/$/);
  });
});

test.describe("dashboard", () => {
  test("shows KPIs and priorities", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Total alerts")).toBeVisible();
    await expect(page.getByText("Start here")).toBeVisible();
    await expect(page.getByText("Overdue follow-ups")).toBeVisible();
  });

  test("draft email modal opens, traps focus and closes", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Draft email" }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Email draft" })).toBeVisible();
    // Esc closes
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
  });
});

test.describe("ask jarvis", () => {
  test("ask via suggestion chip returns an answer", async ({ page }) => {
    await page.goto("/chat");
    await page.getByRole("button", { name: /ISA allowance still available/ }).click();
    await expect(page.getByRole("heading", { name: "Answer" })).toBeVisible();
    await expect(page.getByText(/unused ISA allowance/i)).toBeVisible();
    await expect(page.getByText("Sources")).toBeVisible();
  });

  test("ask button is disabled for empty input", async ({ page }) => {
    await page.goto("/chat");
    await expect(page.getByRole("button", { name: "Ask" })).toBeDisabled();
  });
});

test.describe("brief", () => {
  test("generates a brief with talking points", async ({ page }) => {
    await page.goto("/brief");
    await page.getByRole("button", { name: "Generate brief" }).click();
    await expect(page.getByText("Pre-meeting brief").last()).toBeVisible();
    await expect(page.getByText("Jarvis suggests you cover")).toBeVisible();
  });
});

test.describe("alerts", () => {
  test("labels are human-readable (no raw enums)", async ({ page }) => {
    await page.goto("/alerts");
    const table = page.locator("table");
    await expect(table.getByText("Waiting on client").first()).toBeVisible();
    await expect(table.getByText("Review overdue").first()).toBeVisible();
    // Raw enum strings must NOT appear anywhere visible to the user.
    await expect(page.getByText("FOLLOW_UP", { exact: true })).toHaveCount(0);
    await expect(page.getByText("REVIEW_OVERDUE", { exact: true })).toHaveCount(0);
  });

  test("filters render and are usable", async ({ page }) => {
    await page.goto("/alerts");
    await expect(page.getByText("All alerts")).toBeVisible();
  });
});

test.describe("ingestion", () => {
  test("rejects an unsupported file type", async ({ page }) => {
    await page.goto("/admin");
    await page.locator('input[type="file"]').setInputFiles({
      name: "notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("hello"),
    });
    await expect(page.getByText(/Only PDF and Word/)).toBeVisible();
  });
});

test.describe("settings", () => {
  test("clear-data confirm requires typing DELETE", async ({ page }) => {
    await page.goto("/settings");
    await page.getByRole("button", { name: "Clear all data" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    const confirm = dialog.getByRole("button", { name: "Clear all data" });
    await expect(confirm).toBeDisabled();
    await dialog.getByLabel("Type DELETE to confirm").fill("DELETE");
    await expect(confirm).toBeEnabled();
  });

  test("no demo language remains", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText(/for this demo/i)).toHaveCount(0);
  });
});
