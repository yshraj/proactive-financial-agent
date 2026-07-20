import { test, expect } from "./fixtures/base";

/**
 * Performance guardrails, chromium desktop only (device emulation and other
 * engines skew timings without adding signal). Budgets are deliberately
 * generous — the dev server compiles on first hit — so failures mean
 * something is badly wrong, not that a run was 5% slower. Measured values
 * are attached as annotations for trend-watching in CI reports.
 */

test.describe("performance guardrails", () => {
  test.skip(
    ({ browserName, isMobile }) => browserName !== "chromium" || !!isMobile,
    "timings are only comparable on desktop Chromium"
  );

  test("dashboard warm load stays within budget", async ({ app, page }, testInfo) => {
    // First visit pays the dev-server compile cost; measure the reload.
    await app.dashboard.goto();
    await app.dashboard.expectLoaded();
    await page.reload();
    await app.dashboard.expectLoaded();

    const timing = await page.evaluate(() => {
      const [nav] = performance.getEntriesByType(
        "navigation"
      ) as PerformanceNavigationTiming[];
      return {
        ttfb: Math.round(nav.responseStart - nav.startTime),
        domContentLoaded: Math.round(nav.domContentLoadedEventEnd - nav.startTime),
        load: Math.round(nav.loadEventEnd - nav.startTime),
      };
    });
    testInfo.annotations.push({
      type: "performance",
      description: `dashboard warm load: ttfb=${timing.ttfb}ms dcl=${timing.domContentLoaded}ms load=${timing.load}ms`,
    });

    expect(timing.ttfb).toBeLessThan(5_000);
    expect(timing.domContentLoaded).toBeLessThan(10_000);
  });

  test("client-side page transition completes within budget", async ({
    app,
    page,
  }, testInfo) => {
    await app.dashboard.goto();
    await app.dashboard.expectLoaded();

    const started = Date.now();
    await app.shell.navigateTo("AI Copilot");
    await app.aiCopilot.expectLoaded();
    const elapsed = Date.now() - started;

    testInfo.annotations.push({
      type: "performance",
      description: `dashboard → copilot transition: ${elapsed}ms`,
    });
    expect(elapsed).toBeLessThan(10_000);
  });

  test("chat answer round trip completes within budget", async ({
    app,
    page,
  }, testInfo) => {
    await app.aiCopilot.goto();
    await app.aiCopilot.expectLoaded();

    const started = Date.now();
    await app.aiCopilot.ask("Which clients have unused ISA allowance?");
    const elapsed = Date.now() - started;

    testInfo.annotations.push({
      type: "performance",
      description: `chat ask → rendered answer: ${elapsed}ms`,
    });
    expect(elapsed).toBeLessThan(10_000);
  });

  test("lazy modules only load when their feature opens", async ({
    app,
    page,
  }) => {
    // The draft-email modal is code-split (LazyDraftEmailModal); its chunk
    // must not be part of the alerts page's initial JS.
    const chunkRequests: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("DraftEmailModal")) chunkRequests.push(request.url());
    });

    await app.alerts.goto();
    await app.alerts.expectLoaded();
    expect(chunkRequests).toHaveLength(0);

    await page.getByRole("button", { name: "Draft email" }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    // Dev mode serves the chunk under its module path; seeing it now proves
    // the split point sits where the feature opens, not on page load.
    expect(chunkRequests.length).toBeGreaterThan(0);
  });
});
