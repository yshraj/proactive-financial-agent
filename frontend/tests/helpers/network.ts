import type { Route } from "@playwright/test";

/** Fulfill a route with an arbitrary JSON payload (deterministic, per-test). */
export function fulfillJson(route: Route, status: number, body: unknown) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}
