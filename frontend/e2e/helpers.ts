import { Page, expect } from "@playwright/test";

/** Attach collectors for console errors and uncaught page errors.
 * Returns an array you can assert is empty at the end of a test. */
export function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const text = msg.text();
      // Ignore network-level noise unrelated to app correctness.
      if (text.includes("Failed to load resource")) return;
      errors.push(`console.error: ${text}`);
    }
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  return errors;
}

/** Navigate via the primary nav, opening the mobile drawer first if needed.
 * Decision is keyed on the nav landmark's visibility (deterministic) rather than
 * the menu button, which can briefly detach during route transitions. */
export async function navigate(page: Page, label: string) {
  const nav = page.getByRole("navigation", { name: "Primary" });
  if (!(await nav.isVisible().catch(() => false))) {
    // Mobile: the Primary nav only exists inside the open drawer.
    await page.getByRole("button", { name: "Open menu" }).click();
    await nav.waitFor({ state: "visible" });
  }
  await nav.getByRole("link", { name: label, exact: true }).click();
}

export async function expectHeading(page: Page, name: string) {
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
}
