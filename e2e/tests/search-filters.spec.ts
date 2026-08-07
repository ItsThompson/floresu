import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import {
  bodyText,
  createBullet,
  createProject,
  createRole,
  createWorklog,
  registerAndOnboard,
} from "../harness/support";

/** The term every seeded item shares, so one query retrieves the whole corpus. */
const TERM = "telemetry";

const WORKLOG_ROLE = "Instrumented telemetry pipeline";
const WORKLOG_PROJECT = "Dashboarded telemetry metrics";
const WORKLOG_UNATTACHED = "Explored telemetry sampling";
const BULLET_ROLE = "Owned telemetry ingestion reliability";
const BULLET_PROJECT = "Built telemetry visualizations";

const TAG_ROLE = "backend";
const TAG_PROJECT = "frontend";

/** Add one tag label to a worklog entry through the real add action. */
async function addTag(request: APIRequestContext, worklogId: number, label: string): Promise<void> {
  const response = await request.post(`/worklog/${worklogId}/tags`, {
    data: { label, action: "add" },
  });
  expect(response.ok(), await bodyText(response)).toBeTruthy();
}

/** Type the shared term and submit the search form. */
async function search(page: Page): Promise<void> {
  await page.getByRole("searchbox", { name: "Search experience" }).fill(TERM);
  await page.getByRole("button", { name: "Search", exact: true }).click();
}

/**
 * Search filters and grouping. A role and a project each carry a raw worklog
 * entry and a library bullet that share a query term; a third worklog entry is
 * unattached. One query retrieves the corpus; the kind, tag, layer, and date
 * filters each narrow membership, results render grouped by source, and the
 * unattached hit stays in the flat ranked list.
 *
 * Filters are asserted for presence and grouping only, never exact rank order:
 * fused embedding rank is not byte-stable with the fake embedder (mirrors
 * library-search.spec.ts and the testing strategy).
 *
 * Kind and tag are exercised in separate searches on purpose: the backend's
 * filter eligibility makes `kinds` restrict to sources and `tags` restrict to
 * worklog entries, so setting both at once leaves no eligible kind. The combined
 * search below therefore stacks source + tag + layer + date together, and the
 * kind filter is proven in its own search.
 */
test("search filters narrow membership together and results group by source", async ({ page }) => {
  await registerAndOnboard(page);
  const role = await createRole(page.request, "Northwind", "Telemetry Platform Engineer");
  const project = await createProject(page.request, "Observability Platform");

  const worklogRole = await createWorklog(page.request, {
    title: WORKLOG_ROLE,
    entryDate: "2026-01-15",
    sourceIds: [role.id],
  });
  const worklogProject = await createWorklog(page.request, {
    title: WORKLOG_PROJECT,
    entryDate: "2026-06-20",
    sourceIds: [project.id],
  });
  await createWorklog(page.request, { title: WORKLOG_UNATTACHED, entryDate: "2026-03-10" });
  await createBullet(page.request, BULLET_ROLE, { sourceIds: [role.id] });
  await createBullet(page.request, BULLET_PROJECT, { sourceIds: [project.id] });
  await addTag(page.request, worklogRole.id, TAG_ROLE);
  // The project entry carries a distinct tag, so a tag filter narrows to one entry.
  await addTag(page.request, worklogProject.id, TAG_PROJECT);

  const topMatches = page.getByRole("region", { name: "Top matches" });
  const bySource = page.getByRole("region", { name: "Grouped by source" });
  const roleGroup = bySource.locator("section").filter({ hasText: role.label });
  const projectGroup = bySource.locator("section").filter({ hasText: project.label });

  // Base search: the whole corpus ranks together, groups by source, and the
  // unattached entry appears in the flat list but under no source group.
  await page.goto("/library");
  await search(page);
  await expect(topMatches.getByText(WORKLOG_ROLE)).toBeVisible();
  await expect(topMatches.getByText(WORKLOG_PROJECT)).toBeVisible();
  await expect(topMatches.getByText(WORKLOG_UNATTACHED)).toBeVisible();
  await expect(topMatches.getByText(BULLET_ROLE)).toBeVisible();
  await expect(topMatches.getByText(BULLET_PROJECT)).toBeVisible();

  await expect(roleGroup.getByText(WORKLOG_ROLE)).toBeVisible();
  await expect(roleGroup.getByText(BULLET_ROLE)).toBeVisible();
  await expect(projectGroup.getByText(WORKLOG_PROJECT)).toBeVisible();
  await expect(projectGroup.getByText(BULLET_PROJECT)).toBeVisible();
  // The unattached hit has no source, so it never joins a source group.
  await expect(bySource.getByText(WORKLOG_UNATTACHED)).toBeHidden();

  // Layer = library: only canonical bullets remain, still grouped by their source.
  await page.goto("/library");
  await page.getByLabel("Layer").selectOption("library");
  await search(page);
  await expect(topMatches.getByText(BULLET_ROLE)).toBeVisible();
  await expect(topMatches.getByText(BULLET_PROJECT)).toBeVisible();
  await expect(roleGroup.getByText(BULLET_ROLE)).toBeVisible();
  await expect(projectGroup.getByText(BULLET_PROJECT)).toBeVisible();
  await expect(page.getByText(WORKLOG_ROLE)).toBeHidden();
  await expect(page.getByText(WORKLOG_PROJECT)).toBeHidden();
  await expect(page.getByText(WORKLOG_UNATTACHED)).toBeHidden();

  // Layer = raw: worklog entries (and sources) remain; bullets drop out.
  await page.goto("/library");
  await page.getByLabel("Layer").selectOption("raw");
  await search(page);
  await expect(topMatches.getByText(WORKLOG_ROLE)).toBeVisible();
  await expect(topMatches.getByText(WORKLOG_PROJECT)).toBeVisible();
  await expect(topMatches.getByText(WORKLOG_UNATTACHED)).toBeVisible();
  await expect(page.getByText(BULLET_ROLE)).toBeHidden();
  await expect(page.getByText(BULLET_PROJECT)).toBeHidden();

  // Kind = Role: only source hits survive, restricted to the role kind; the
  // project (a different kind) and every worklog/bullet hit drop out.
  await page.goto("/library");
  await page.getByRole("checkbox", { name: "Role", exact: true }).check();
  await search(page);
  await expect(topMatches.getByText(role.label)).toBeVisible();
  await expect(roleGroup).toBeVisible();
  // The project source label also renders as a filter control, so scope the
  // "project dropped" checks to the result regions rather than the whole page.
  await expect(topMatches.getByText(project.label)).toBeHidden();
  await expect(projectGroup).toBeHidden();
  await expect(page.getByText(WORKLOG_ROLE)).toBeHidden();
  await expect(page.getByText(BULLET_ROLE)).toBeHidden();

  // Tag = backend: only the worklog entry carrying that tag remains; the
  // frontend-tagged entry, the untagged entry, and every bullet drop out.
  await page.goto("/library");
  await page.getByRole("checkbox", { name: TAG_ROLE }).check();
  await search(page);
  await expect(topMatches.getByText(WORKLOG_ROLE)).toBeVisible();
  await expect(roleGroup.getByText(WORKLOG_ROLE)).toBeVisible();
  await expect(page.getByText(WORKLOG_PROJECT)).toBeHidden();
  await expect(page.getByText(WORKLOG_UNATTACHED)).toBeHidden();
  await expect(page.getByText(BULLET_ROLE)).toBeHidden();

  // Date window (Jan-Feb): the in-window worklog entry remains; later entries and
  // every bullet (bullets carry no intrinsic date) drop out.
  await page.goto("/library");
  await page.getByLabel("From date").fill("2026-01-01");
  await page.getByLabel("To date").fill("2026-02-28");
  await search(page);
  await expect(topMatches.getByText(WORKLOG_ROLE)).toBeVisible();
  await expect(page.getByText(WORKLOG_PROJECT)).toBeHidden();
  await expect(page.getByText(WORKLOG_UNATTACHED)).toBeHidden();
  await expect(page.getByText(BULLET_ROLE)).toBeHidden();

  // Combined: source + tag + layer (raw) + date applied together narrow to the one
  // entry that satisfies all four, still grouped under its source.
  await page.goto("/library");
  await page.getByRole("checkbox", { name: role.label }).check();
  await page.getByRole("checkbox", { name: TAG_ROLE }).check();
  await page.getByLabel("Layer").selectOption("raw");
  await page.getByLabel("From date").fill("2026-01-01");
  await page.getByLabel("To date").fill("2026-02-28");
  await search(page);
  await expect(topMatches.getByText(WORKLOG_ROLE)).toBeVisible();
  await expect(roleGroup.getByText(WORKLOG_ROLE)).toBeVisible();
  await expect(page.getByText(WORKLOG_PROJECT)).toBeHidden();
  await expect(page.getByText(WORKLOG_UNATTACHED)).toBeHidden();
  await expect(page.getByText(BULLET_ROLE)).toBeHidden();
  await expect(page.getByText(BULLET_PROJECT)).toBeHidden();
  await expect(projectGroup).toBeHidden();
});
