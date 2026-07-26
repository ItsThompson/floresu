import { expect, test } from "@playwright/test";

import { PASSWORD, uniqueEmail } from "../harness/support";

/**
 * Anchor flow 1 — INITIALIZE. Sign up drives the four-step wizard, lands on Home,
 * and (the persisted-onboarding guarantee) the wizard does not reappear on
 * reload. Then the new user seeds the record: a profile role, a worklog entry,
 * and a first living resume, all through the browser against the real backend.
 */
test("sign up, onboard, and seed the first record", async ({ page }) => {
  const email = uniqueEmail("initialize");

  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();

  // Wizard: Welcome -> Choose path -> Connect agent -> How it works.
  await expect(page.getByRole("heading", { name: "Welcome to Floresu" })).toBeVisible();
  await page.getByRole("button", { name: "Get started" }).click();
  await expect(page.getByRole("heading", { name: "How do you want to start?" })).toBeVisible();
  await page.getByRole("button", { name: /Connect your agent/ }).click();
  await expect(page.getByRole("heading", { name: "Connect your agent" })).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "How Floresu works" })).toBeVisible();
  await page.getByRole("button", { name: "Finish" }).click();

  // Landed on Home.
  await expect(page).toHaveURL("/");
  await expect(page.getByRole("heading", { name: "Home", level: 1 })).toBeVisible();

  // The wizard does not reappear on reload (onboarding is persisted server-side).
  await page.reload();
  await expect(page).toHaveURL("/");
  await expect(page.getByRole("heading", { name: "Home", level: 1 })).toBeVisible();

  // Add profile data: a role.
  await page.goto("/profile/sources/new?kind=role");
  await page.getByLabel("Company").fill("Acme Corp");
  await page.getByLabel("Job title").fill("Staff Engineer");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/profile\/sources\/\d+$/);
  await expect(page.getByRole("heading", { name: /Acme Corp/ })).toBeVisible();

  // Add a worklog entry.
  await page.goto("/worklog");
  await page.getByRole("button", { name: /Add entry/ }).first().click();
  const form = page.getByRole("form", { name: "Add entry" });
  await form.getByLabel("Title").fill("Shipped the billing rewrite");
  await form.getByLabel("Date").fill("2026-02-10");
  await form.getByRole("button", { name: "Save entry" }).click();
  await expect(page.getByText("Shipped the billing rewrite")).toBeVisible();

  // Create the first living resume.
  await page.goto("/resumes");
  await page.getByRole("button", { name: /New resume/ }).click();
  const dialog = page.getByRole("dialog", { name: "New resume" });
  await dialog.getByLabel("Title").fill("Backend Engineer");
  await dialog.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/resumes\/\d+$/);
  await expect(page.getByRole("textbox", { name: "Resume title" })).toHaveValue("Backend Engineer");
});

/**
 * Anchor flow 1b: INITIALIZE, manual path. "Start manually" is the alternative
 * to "Connect your agent": it persists onboarding and lands the user on an open
 * worklog entry form via client-side navigation, so a manual starter can type
 * their first entry immediately. Reload proves onboarding persisted server-side.
 */
test("start manually opens the first worklog entry form", async ({ page }) => {
  const email = uniqueEmail("manual-start");

  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();

  // Wizard: Welcome -> Choose path -> Start manually.
  await expect(page.getByRole("heading", { name: "Welcome to Floresu" })).toBeVisible();
  await page.getByRole("button", { name: "Get started" }).click();
  await expect(page.getByRole("heading", { name: "How do you want to start?" })).toBeVisible();
  await page.getByRole("button", { name: /Start manually/ }).click();

  // Landed on the worklog with the new-entry form open, via client-side nav.
  await expect(page).toHaveURL(/\/worklog\?new=1$/);
  await expect(page.getByRole("form", { name: "Add entry" })).toBeVisible();

  // The wizard does not reappear on reload (onboarding is persisted server-side).
  await page.reload();
  await expect(page.getByRole("heading", { name: "Worklog", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Welcome to Floresu" })).not.toBeVisible();
});
