import { expect, test } from "@playwright/test";

import { createBullet, createRole, createWorklog, registerAndOnboard } from "../harness/support";

/**
 * Hybrid search in the Library: a worklog entry and a bullet share a term and are
 * ranked together; a source filter narrows the results (an unattached entry
 * drops); a non-matching query returns nothing; and the backend enforces that an
 * empty query returns no ranked hits (never a full dump).
 */
test("hybrid search ranks a worklog entry and a bullet, and filters narrow", async ({ page }) => {
  await registerAndOnboard(page);
  const role = await createRole(page.request, "Initech", "Platform Engineer");
  await createWorklog(page.request, {
    title: "Migrated kubernetes ingress",
    entryDate: "2026-01-20",
    sourceIds: [role.id],
  });
  await createWorklog(page.request, {
    title: "Debugged kubernetes DNS flakiness",
    entryDate: "2026-01-22",
  });
  await createBullet(page.request, "Owned kubernetes platform reliability", {
    sourceIds: [role.id],
  });

  await page.goto("/library");
  await page.getByRole("searchbox", { name: "Search experience" }).fill("kubernetes");
  await page.getByRole("button", { name: "Search", exact: true }).click();

  // Ranked together: the flat "Top matches" list carries both a worklog hit and a
  // bullet hit, tagged by kind.
  const topMatches = page.getByRole("region", { name: "Top matches" });
  await expect(topMatches).toBeVisible();
  await expect(topMatches.getByText("Worklog", { exact: true }).first()).toBeVisible();
  await expect(topMatches.getByText("Bullet", { exact: true }).first()).toBeVisible();
  await expect(topMatches.getByText("Migrated kubernetes ingress")).toBeVisible();
  await expect(topMatches.getByText("Debugged kubernetes DNS flakiness")).toBeVisible();

  // Filter to the source and re-search: the unattached "DNS" entry drops.
  await page.getByRole("checkbox", { name: role.label }).check();
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(topMatches.getByText("Debugged kubernetes DNS flakiness")).toBeHidden();
  await expect(topMatches.getByText("Migrated kubernetes ingress")).toBeVisible();
  await expect(topMatches.getByText("Owned kubernetes platform reliability")).toBeVisible();

  // A non-matching query returns nothing.
  await page.getByRole("checkbox", { name: role.label }).uncheck();
  await page.getByRole("searchbox", { name: "Search experience" }).fill("zxqwvnonsenseterm");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("No matches. Try a different query or fewer filters.")).toBeVisible();

  // Boundary: the backend returns no ranked hits for an empty query (never a dump).
  const empty = await page.request.post("/search", { data: { query: "", filters: {} } });
  expect(empty.ok()).toBeTruthy();
  expect(((await empty.json()) as { ranked: unknown[] }).ranked).toHaveLength(0);
});
