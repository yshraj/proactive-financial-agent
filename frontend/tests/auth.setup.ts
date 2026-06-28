import fs from "node:fs";
import path from "node:path";
import { test } from "@playwright/test";
import { LoginPage } from "./pages/LoginPage";

const authFile = path.resolve(__dirname, ".auth/user.json");

test("authenticate once for protected routes", async ({ page }) => {
  fs.mkdirSync(path.dirname(authFile), { recursive: true });

  const login = new LoginPage(page);
  await login.goto("/dashboard");
  await login.signIn();
  await page.waitForURL(/\/dashboard/);
  await page.context().storageState({ path: authFile });
});
