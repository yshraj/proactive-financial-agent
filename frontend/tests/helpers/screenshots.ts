import fs from "node:fs";
import path from "node:path";
import type { Page, TestInfo } from "@playwright/test";

const SCREENSHOT_ROOT = path.resolve(__dirname, "../../playwright-results/screenshots");

/** Save a full-page screenshot to playwright-results/screenshots/{project}/{name}.png */
export async function captureScreenshot(
  page: Page,
  name: string,
  testInfo?: TestInfo
) {
  const project = testInfo?.project.name ?? "manual";
  const dir = path.join(SCREENSHOT_ROOT, project);
  fs.mkdirSync(dir, { recursive: true });
  const safeName = name.replace(/[^\w-]+/g, "-").toLowerCase();
  await page.screenshot({
    path: path.join(dir, `${safeName}.png`),
    fullPage: true,
  });
}

/** @deprecated Prefer captureScreenshot — kept for existing specs */
export async function captureMajorPageScreenshot(
  page: Page,
  testInfo: TestInfo,
  name: string
) {
  await captureScreenshot(page, name, testInfo);
}
