import fs from "node:fs";
import path from "node:path";
import { test } from "@playwright/test";
import { LoginPage } from "./pages/LoginPage";

const authFile = path.resolve(__dirname, ".auth/user.json");

/** Every route the suite visits. Warmed once so the Next.js dev server's
 * on-demand compiler never stalls a client-side navigation mid-test when
 * parallel workers all hit cold routes at once. */
const APP_ROUTES = [
  "/",
  "/login",
  "/dashboard",
  "/chat",
  "/brief",
  "/clients",
  "/clients/c1",
  "/alerts",
  "/admin",
  "/settings",
];

test("authenticate once for protected routes", async ({ page, request }) => {
  fs.mkdirSync(path.dirname(authFile), { recursive: true });

  const login = new LoginPage(page);
  await login.goto("/dashboard");
  await login.signIn();
  await page.waitForURL(/\/dashboard/);
  await page.context().storageState({ path: authFile });

  // Failures don't matter here — real coverage happens in the specs.
  await Promise.all(APP_ROUTES.map((route) => request.get(route).catch(() => {})));
});
