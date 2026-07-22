import { test, expect } from "./fixtures/base";
import { confirmCreditCostIfShown } from "./helpers/credits";

/**
 * Failure-path coverage: broken URLs, API errors, network loss, rejected
 * uploads, and tablet layout. API failures are injected with page.route so
 * they are deterministic and independent of the mock server's happy paths.
 */

test.describe("404 handling", () => {
  test("unknown route shows the branded 404 page with a way home", async ({ page }) => {
    await page.goto("/this-page-does-not-exist");
    await expect(page.getByText("Error 404")).toBeVisible();
    await expect(
      page.getByRole("heading", { level: 1, name: "This page doesn't exist" })
    ).toBeVisible();

    await page.getByTestId("error-page-home").click();
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test("404 page renders without the app shell", async ({ page }) => {
    await page.goto("/nope/nested/route");
    await expect(page.getByText("Error 404")).toBeVisible();
    // No sidebar navigation on the bare error page.
    await expect(page.getByTestId("nav-link-dashboard")).toHaveCount(0);
  });
});

test.describe("API failure states", () => {
  test("dashboard shows a recoverable error when pulse returns 500", async ({ app, page }) => {
    let failNext = true;
    await page.route("**/api/monitor/pulse*", async (route) => {
      if (failNext) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Internal error" }),
        });
        return;
      }
      await route.fallback();
    });

    await app.dashboard.goto();
    const errorState = page.getByRole("alert").filter({ hasText: /wrong|error/i }).first();
    await expect(errorState).toBeVisible();

    // Recovery: the retry affordance refetches and the dashboard loads.
    failNext = false;
    await page.getByRole("button", { name: "Try again" }).first().click();
    await app.dashboard.expectLoaded();
  });

  test("clients page surfaces network loss with a retry affordance", async ({ app, page }) => {
    // Hard network failure on the clients endpoint; the page must show an
    // error with a retry button rather than a blank card or endless spinner.
    await page.route("**/api/monitor/clients*", (route) => route.abort("failed"));

    await app.clients.goto();
    const errorState = page.getByRole("alert").filter({ hasText: /wrong|error|failed/i }).first();
    await expect(errorState).toBeVisible();
    await expect(errorState.getByRole("button", { name: "Try again" })).toBeVisible();
  });

  test("settings audit log failure is visible, not silently empty", async ({ page }) => {
    await page.route("**/api/compliance/audit*", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal error" }),
      })
    );

    await page.goto("/settings");
    const auditCard = page.getByTestId("audit-log-card");
    await expect(auditCard.getByRole("alert")).toBeVisible();
    await expect(auditCard.getByText("Couldn't load the audit log.")).toBeVisible();
  });

  test("unauthorized API responses degrade to an error state, not a blank page", async ({
    page,
  }) => {
    // Simulates an expired session against a secured backend: the API starts
    // rejecting with 401 while the SPA shell is already loaded.
    await page.route("**/api/monitor/pulse*", (route) =>
      route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "Authentication required. Please sign in to continue.",
          error: {
            code: "unauthorized",
            message: "Authentication required. Please sign in to continue.",
            retryable: false,
          },
        }),
      })
    );

    await page.goto("/dashboard");
    await expect(page.getByRole("alert").first()).toBeVisible();
    await expect(page.getByText(/authentication required/i)).toBeVisible();
  });
});

test.describe("upload validation", () => {
  test("rejects a file whose content does not match its extension", async ({ app, page }) => {
    await app.ingestion.goto();
    await app.ingestion.expectLoaded();

    // .pdf name, but plain-text bytes: the client-side magic check must
    // reject it before any network call.
    let uploadRequested = false;
    await page.route("**/api/ingest/upload*", (route) => {
      uploadRequested = true;
      return route.fallback();
    });

    await page.getByTestId("document-upload-input").setInputFiles({
      name: "fake-report.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("this is not a pdf at all"),
    });

    const row = page.getByTestId("upload-status-item").filter({ hasText: "fake-report.pdf" });
    await expect(row).toContainText(/does not match its extension/i);
    expect(uploadRequested).toBe(false);
  });

  test("rejects unsupported file types", async ({ app, page }) => {
    await app.ingestion.goto();
    await page.getByTestId("document-upload-input").setInputFiles({
      name: "photo.png",
      mimeType: "image/png",
      buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    });
    const row = page.getByTestId("upload-status-item").filter({ hasText: "photo.png" });
    await expect(row).toContainText(/Only PDF, Word/i);
  });

  test("accepts markdown and plain-text uploads", async ({ app, page }) => {
    await app.ingestion.goto();
    await page.getByTestId("document-upload-input").setInputFiles([
      {
        name: "meeting-notes.md",
        mimeType: "text/markdown",
        buffer: Buffer.from("# Client review\n\nDiscussed pension consolidation and ISA top-up."),
      },
      {
        name: "call-summary.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("Call with client about protection cover renewal."),
      },
    ]);
    for (const name of ["meeting-notes.md", "call-summary.txt"]) {
      const row = page.getByTestId("upload-status-item").filter({ hasText: name });
      await expect(row).toContainText(/Uploading|Done|Stored/);
      await expect(row).not.toContainText(/accepted|Invalid|does not match/i);
    }
  });

  test("rejects a binary masquerading as a text file", async ({ app, page }) => {
    await app.ingestion.goto();
    await page.getByTestId("document-upload-input").setInputFiles({
      name: "innocent.txt",
      // NUL bytes: executables/binaries renamed to .txt must fail client-side.
      buffer: Buffer.from([0x4d, 0x5a, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00]),
      mimeType: "text/plain",
    });
    const row = page.getByTestId("upload-status-item").filter({ hasText: "innocent.txt" });
    await expect(row).toContainText(/does not match its extension/i);
  });

  test("surfaces duplicate uploads distinctly", async ({ app, page }) => {
    await page.route("**/api/ingest/upload-async", (route) =>
      route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({
          detail: {
            code: "DUPLICATE",
            message: "This file has the same content as one already in the system.",
            existing_id: "00000000-0000-0000-0000-00000000dupe",
            existing_filename: "original.pdf",
          },
        }),
      })
    );

    await app.ingestion.goto();
    await page.getByTestId("document-upload-input").setInputFiles({
      name: "duplicate.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"),
    });
    const row = page.getByTestId("upload-status-item").filter({ hasText: "duplicate.pdf" });
    await expect(row).toContainText(/original\.pdf.*Not stored again/);
  });
});

test.describe("ingestion pipeline UX", () => {
  test("upload shows stage progress before completing", async ({ app, page }) => {
    await app.ingestion.goto();
    await app.ingestion.expectLoaded();
    await page.getByTestId("document-upload-input").setInputFiles({
      name: "progress-demo.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"),
    });

    const row = page.getByTestId("upload-status-item").filter({ hasText: "progress-demo.pdf" });
    // Mock job reports PROCESSING 55% on the first poll: the determinate
    // progress bar must be visible with a real value before completion.
    const bar = row.getByTestId("upload-progress-bar");
    await expect(bar).toBeVisible();
    await expect(bar).toHaveAttribute("aria-valuenow", /\d+/);
    await expect(row).toContainText(/%/);

    await expect(row).toContainText(/Done/, { timeout: 15_000 });
    await expect(bar).toBeHidden();
  });

  test("same-content document in another format is linked, not duplicated", async ({
    app,
    page,
  }) => {
    // Simulate the backend's content-level dedup outcome via the job status.
    await page.route("**/api/ingest/jobs/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "job-ct-dup",
          kind: "upload",
          filename: "whitfield.pdf",
          status: "DONE",
          progress: 100,
          message: 'Content matches "whitfield-fact-find.md" — no duplicate records created.',
          document_id: "job-ct-dup",
          error: null,
        }),
      })
    );
    await app.ingestion.goto();
    await page.getByTestId("document-upload-input").setInputFiles({
      name: "whitfield.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"),
    });
    const row = page.getByTestId("upload-status-item").filter({ hasText: "whitfield.pdf" });
    await expect(row).toContainText(/Content matches .* no duplicate records created/i, {
      timeout: 15_000,
    });
  });

  test("brief Regenerate bypasses the server cache with refresh=true", async ({ app, page }) => {
    await app.meetingBrief.goto();
    await app.meetingBrief.expectLoaded();
    await app.meetingBrief.generateBrief();

    const regenRequest = page.waitForRequest(
      (r) =>
        r.url().includes("/api/chat/brief") &&
        r.method() === "POST" &&
        r.postDataJSON()?.refresh === true
    );
    await page.getByTestId("regenerate-brief-button").click();
    await confirmCreditCostIfShown(page);
    await regenRequest;
    await expect(page.getByTestId("generated-brief")).toBeVisible();
  });
});

test.describe("tablet layout", () => {
  test("tablet-width viewport gets the full sidebar navigation", async ({ app, page }) => {
    await page.setViewportSize({ width: 834, height: 1112 }); // iPad Air portrait
    await app.dashboard.goto();
    await app.dashboard.expectLoaded();
    // At >= md the persistent sidebar replaces the mobile drawer.
    await expect(page.getByTestId("nav-link-clients")).toBeVisible();
    await expect(page.getByTestId("mobile-menu-button")).toBeHidden();

    await app.shell.navigateTo("Clients");
    await app.clients.expectLoaded();
  });
});
