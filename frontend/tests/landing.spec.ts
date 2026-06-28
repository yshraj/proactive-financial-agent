import { test } from "./fixtures/base";
import { captureMajorPageScreenshot } from "./helpers/screenshots";

test.describe("landing page", () => {
  test("loads successfully", async ({ app, page }, testInfo) => {
    await app.landing.goto();
    await app.landing.expectLoaded();
    await captureMajorPageScreenshot(page, testInfo, "landing");
  });
});
