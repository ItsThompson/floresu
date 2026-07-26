import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import {
  bodyText,
  createProject,
  createRole,
  createWorklog,
  registerAndOnboard,
} from "../harness/support";

// Titles are kept mutually non-substring so exact-text lookups never collide.
const AUTH = "Shipped the auth revamp"; // May, role, backend  -> matches all three filters
const MIGRATION = "Wrote the migration plan"; // March, role, backend
const ONBOARDING = "Polished the onboarding UI"; // May, role, frontend
const INGEST = "Tuned the ingest pipeline"; // May, project, backend
const DESIGN = "Drafted the design system"; // March, project, frontend

const BACKEND = "backend";
const FRONTEND = "frontend";

const MAY_RANGE = { from: "2026-05-01", to: "2026-05-31" } as const;

/** Add one tag label to an entry through the real POST /worklog/{id}/tags add action. */
async function addTag(request: APIRequestContext, worklogId: number, label: string): Promise<void> {
  const response = await request.post(`/worklog/${worklogId}/tags`, {
    data: { label, action: "add" },
  });
  expect(response.ok(), await bodyText(response)).toBeTruthy();
}

/** Seed one worklog entry attached to a source and carrying a single tag. */
async function seedEntry(
  request: APIRequestContext,
  entry: { title: string; entryDate: string; sourceId: number; tag: string },
): Promise<void> {
  const { id } = await createWorklog(request, {
    title: entry.title,
    entryDate: entry.entryDate,
    sourceIds: [entry.sourceId],
  });
  await addTag(request, id, entry.tag);
}

/** Assert the timeline shows exactly the expected titles: `present` render, `absent` are gone. */
async function expectTitles(page: Page, present: string[], absent: string[]): Promise<void> {
  for (const title of present) {
    await expect(page.getByText(title, { exact: true })).toBeVisible();
  }
  for (const title of absent) {
    await expect(page.getByText(title, { exact: true })).toHaveCount(0);
  }
}

/**
 * The global worklog timeline groups entries by month (newest first) and its
 * source, tag, and date-range filters each narrow the list and combine. Seed two
 * sources (a role and a project) and five entries spanning two months, with tags
 * and distinct dates, so one entry matches all three filters while each of the
 * others matches only two. Drive /worklog: read the grouping, apply each filter
 * on its own, then all three together. Assert month grouping and membership, that
 * every filter narrows, and that the combination keeps only the entry matching
 * all active filters. Ordering within a month is not asserted.
 */
test("worklog timeline groups by month newest-first; source, tag, and date filters narrow and combine", async ({
  page,
}) => {
  await registerAndOnboard(page);

  const role = await createRole(page.request, "Globex", "Senior Engineer");
  const project = await createProject(page.request, "Platform rewrite");

  await seedEntry(page.request, { title: AUTH, entryDate: "2026-05-08", sourceId: role.id, tag: BACKEND });
  await seedEntry(page.request, { title: MIGRATION, entryDate: "2026-03-05", sourceId: role.id, tag: BACKEND });
  await seedEntry(page.request, { title: ONBOARDING, entryDate: "2026-05-14", sourceId: role.id, tag: FRONTEND });
  await seedEntry(page.request, { title: INGEST, entryDate: "2026-05-22", sourceId: project.id, tag: BACKEND });
  await seedEntry(page.request, { title: DESIGN, entryDate: "2026-03-18", sourceId: project.id, tag: FRONTEND });

  await page.goto("/worklog");

  // Grouped by month, newest month first: the May group precedes the March group.
  const monthRegions = page.getByRole("region", { name: /2026/ });
  await expect(monthRegions).toHaveCount(2);
  await expect(monthRegions.nth(0)).toHaveAccessibleName("May 2026");
  await expect(monthRegions.nth(1)).toHaveAccessibleName("March 2026");

  // Membership: each entry sits in its own month group (within-month order is not asserted).
  const may = page.getByRole("region", { name: "May 2026" });
  const march = page.getByRole("region", { name: "March 2026" });
  for (const title of [AUTH, ONBOARDING, INGEST]) {
    await expect(may.getByText(title, { exact: true })).toBeVisible();
  }
  for (const title of [MIGRATION, DESIGN]) {
    await expect(march.getByText(title, { exact: true })).toBeVisible();
  }

  // Source filter narrows to the role's entries; the project's entries drop.
  await page.getByLabel("Source").selectOption({ value: String(role.id) });
  await expectTitles(page, [AUTH, MIGRATION, ONBOARDING], [INGEST, DESIGN]);
  await page.getByRole("button", { name: "Clear" }).click();

  // Tag filter narrows to the backend-tagged entries; the frontend ones drop.
  await page.getByLabel("Tag").selectOption({ value: BACKEND });
  await expectTitles(page, [AUTH, MIGRATION, INGEST], [ONBOARDING, DESIGN]);
  await page.getByRole("button", { name: "Clear" }).click();

  // Date-range filter narrows to May; the March entries drop.
  await page.getByLabel("From").fill(MAY_RANGE.from);
  await page.getByLabel("To").fill(MAY_RANGE.to);
  await expectTitles(page, [AUTH, ONBOARDING, INGEST], [MIGRATION, DESIGN]);
  await page.getByRole("button", { name: "Clear" }).click();

  // Combined: source + tag + date apply together. Only the entry matching all
  // three remains; each dropped entry matches two of the filters but fails one.
  await page.getByLabel("Source").selectOption({ value: String(role.id) });
  await page.getByLabel("Tag").selectOption({ value: BACKEND });
  await page.getByLabel("From").fill(MAY_RANGE.from);
  await page.getByLabel("To").fill(MAY_RANGE.to);
  await expectTitles(page, [AUTH], [MIGRATION, ONBOARDING, INGEST, DESIGN]);
  await expect(may.getByText(AUTH, { exact: true })).toBeVisible();
  await expect(monthRegions).toHaveCount(1);
});
