import fs from "node:fs";
import path from "node:path";
import type { Page, TestInfo } from "@playwright/test";

export async function captureMajorPageScreenshot(
  page: Page,
  testInfo: TestInfo,
  name: string
) {
  const dir = testInfo.outputPath("successful-screenshots");
  fs.mkdirSync(dir, { recursive: true });
  await page.screenshot({
    path: path.join(dir, `${name}-${testInfo.project.name}.png`),
    fullPage: true,
  });
}
