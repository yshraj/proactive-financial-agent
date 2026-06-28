import { test } from "@playwright/test";
import path from "path";

// Captures full-page screenshots for the QA evidence set.
// Output: ../review-screenshots/after-<page>-<project>.png
const OUT = path.resolve(__dirname, "..", "..", "review-screenshots");

const PAGES = [
  { name: "dashboard", path: "/" },
  { name: "chat", path: "/chat" },
  { name: "brief", path: "/brief" },
  { name: "ingestion", path: "/admin" },
  { name: "alerts", path: "/alerts" },
  { name: "settings", path: "/settings" },
];

for (const p of PAGES) {
  test(`screenshot ${p.name}`, async ({ page }, testInfo) => {
    await page.goto(p.path);
    await page.waitForTimeout(900);
    await page.screenshot({
      path: path.join(OUT, `after-${p.name}-${testInfo.project.name}.png`),
      fullPage: true,
    });
  });
}

test("screenshot chat answer", async ({ page }, testInfo) => {
  await page.goto("/chat");
  await page.getByRole("button", { name: /ISA allowance still available/ }).click();
  await page.getByRole("heading", { name: "Answer" }).waitFor();
  await page.waitForTimeout(400);
  await page.screenshot({
    path: path.join(OUT, `after-chat-answer-${testInfo.project.name}.png`),
    fullPage: true,
  });
});
