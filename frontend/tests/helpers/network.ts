import type { Page, Route } from "@playwright/test";

/**
 * Network fault-injection helpers. All failures are injected with page.route
 * so they are deterministic and per-test; nothing here mutates the shared
 * mock server. Timing helpers delay the *response*, never the test itself —
 * assertions keep relying on Playwright auto-waiting.
 */

/** Exact detail string the FastAPI backend puts in its structured 429 body. */
export const RATE_LIMIT_DETAIL =
  "Too many requests in a short period. Wait a moment and try again.";

/** Short-window abuse protection is distinct from lifetime AI credits. */
export type LimitType = "request";

type RateLimitOptions = {
  /** Seconds until the window resets (drives Retry-After / reset_at). */
  retryAfterSeconds?: number;
  /** Override the human-readable detail; null omits it entirely. */
  detail?: string | null;
};

/**
 * Body + headers mirroring backend/app/main.py `rate_limit_handler`:
 * {error, limit_type, reset_at, detail} plus Retry-After / X-RateLimit-*.
 */
export function rateLimitResponse(
  limitType: LimitType,
  { retryAfterSeconds = 60, detail = RATE_LIMIT_DETAIL }: RateLimitOptions = {}
) {
  const resetAt = new Date(Date.now() + retryAfterSeconds * 1000).toISOString();
  const body: Record<string, unknown> = {
    error: "rate_limit",
    limit_type: limitType,
    reset_at: resetAt,
  };
  if (detail !== null) body.detail = detail;
  return {
    status: 429,
    contentType: "application/json",
    headers: {
      "Retry-After": String(retryAfterSeconds),
      "X-RateLimit-Limit": "30",
      "X-RateLimit-Remaining": "0",
      "X-RateLimit-Reset": String(Math.round(Date.now() / 1000) + retryAfterSeconds),
    },
    body: JSON.stringify(body),
  };
}

/** Fulfill a route with the backend's structured 429 shape. */
export function fulfillRateLimited(
  route: Route,
  limitType: LimitType,
  options?: RateLimitOptions
) {
  return route.fulfill(rateLimitResponse(limitType, options));
}

/** Fulfill a route with an arbitrary JSON payload. */
export function fulfillJson(route: Route, status: number, body: unknown) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

/**
 * Rate-limit the first `times` matching requests, then let traffic through.
 * Returns a live counter so specs can assert exactly how many requests were
 * blocked vs retried.
 */
export async function rateLimitFirst(
  page: Page,
  urlGlob: string,
  limitType: LimitType,
  times = 1,
  options?: RateLimitOptions
): Promise<{ blocked: () => number; total: () => number }> {
  let blocked = 0;
  let total = 0;
  await page.route(urlGlob, async (route) => {
    total += 1;
    if (blocked < times) {
      blocked += 1;
      await fulfillRateLimited(route, limitType, options);
      return;
    }
    await route.fallback();
  });
  return { blocked: () => blocked, total: () => total };
}

/**
 * Delay matching requests by `ms` before forwarding them, so loading states
 * stay observable. The latency lives in the route handler — tests still use
 * auto-waiting assertions, never waitForTimeout.
 */
export async function delayRequests(page: Page, urlGlob: string, ms: number) {
  await page.route(urlGlob, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, ms));
    await route.fallback();
  });
}

/** Count matching requests without altering them. */
export async function countRequests(
  page: Page,
  urlPart: string,
  method = "POST"
): Promise<() => number> {
  let count = 0;
  page.on("request", (request) => {
    if (request.url().includes(urlPart) && request.method() === method) count += 1;
  });
  return () => count;
}
