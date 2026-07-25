import type { Page } from "@playwright/test";

// Network-layer noise that is either expected (failure-path tests
// deliberately 500 requests) or a browser teardown race — not an application
// bug. The fixture is meant to catch app-level console errors (React
// warnings, thrown exceptions), so these are filtered.
const IGNORED_CONSOLE_PATTERNS = [
  "Failed to load resource",
  "Abort fetching component",
  "net::ERR_FAILED", // Chromium aborted route
];

export function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];

  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (IGNORED_CONSOLE_PATTERNS.some((p) => text.includes(p))) return;
    errors.push(`console.error: ${text}`);
  });

  page.on("pageerror", (error) => {
    errors.push(`pageerror: ${error.message}`);
  });

  return errors;
}
