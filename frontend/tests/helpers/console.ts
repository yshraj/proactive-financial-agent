import type { Page } from "@playwright/test";

export function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];

  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (text.includes("Failed to load resource")) return;
    errors.push(`console.error: ${text}`);
  });

  page.on("pageerror", (error) => {
    errors.push(`pageerror: ${error.message}`);
  });

  return errors;
}
