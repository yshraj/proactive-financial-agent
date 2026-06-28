import { test, expect } from "./fixtures/base";

test.describe("responsive layout", () => {
  test("app navigation works on desktop and mobile projects", async ({ app, page }, testInfo) => {
    await app.dashboard.goto();
    await app.dashboard.expectLoaded();

    if (testInfo.project.name.includes("mobile")) {
      await expect(page.getByTestId("mobile-menu-button")).toBeVisible();
    }

    await app.shell.navigateTo("AI Copilot");
    await app.aiCopilot.expectLoaded();

    await app.shell.navigateTo("Dashboard");
    await app.dashboard.expectLoaded();
  });
});
