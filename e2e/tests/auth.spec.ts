import { expect, test } from "@playwright/test";

import { registerAndOnboard } from "../harness/support";

/**
 * Auth: login, session resume across a reload (the rotating-refresh path), and
 * logout. The account is created via the API; the browser drives the human
 * login/logout surface and the reload-resume that exercises `/auth/refresh`.
 */
test("login, resume on reload, and logout", async ({ page }) => {
  const { email, password } = await registerAndOnboard(page);

  // Start signed out.
  await page.request.post("/auth/logout");
  await page.context().clearCookies();

  // Login through the form.
  await page.goto("/signin");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");
  await expect(page.getByRole("heading", { name: "Home", level: 1 })).toBeVisible();

  // Reload resumes the session (refresh-token rotation), still authenticated.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Home", level: 1 })).toBeVisible();
  await expect(page.getByText(email).first()).toBeVisible();

  // Logout returns to the chrome-free sign-in screen.
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/signin$/);

  // A guarded route now bounces to sign-in.
  await page.goto("/worklog");
  await expect(page).toHaveURL(/\/signin$/);
});
