import { expect, test, type APIRequestContext } from "@playwright/test";

import { bodyText, createBullet, createWorklog, registerAndOnboard } from "../harness/support";

/** The skill name curated through the browser; also a worklog tag label, so its usage count derives. */
const MATCHED_SKILL = "TypeScript";
/** A tag used on the worklog but never curated: it must not auto-promote into a skill. */
const UNCURATED_TAG = "GraphQL";

/** The read shape GET /skills returns (usage_count derived, sort_order curated). */
interface SkillWire {
  id: number;
  name: string;
  usage_count: number;
  sort_order: number;
  archived_at: string | null;
}

/** Add one tag label to an entry through the real POST /worklog/{id}/tags add action. */
async function addWorklogTag(
  request: APIRequestContext,
  worklogId: number,
  label: string,
): Promise<void> {
  const response = await request.post(`/worklog/${worklogId}/tags`, {
    data: { label, action: "add" },
  });
  expect(response.ok(), await bodyText(response)).toBeTruthy();
}

/** Read the active skills list via GET /skills, asserting ok with the body as the message. */
async function listSkills(request: APIRequestContext): Promise<SkillWire[]> {
  const response = await request.get("/skills");
  expect(response.ok(), await bodyText(response)).toBeTruthy();
  return (await response.json()) as SkillWire[];
}

/**
 * C4: curate the skills list and prove the derived usage count. The account is
 * seeded with two worklog entries tagged with a skill's name and one tagged with
 * a term left uncurated, plus a library bullet framing the tagged entry. Skills
 * are added, renamed, and archived as genuine browser interactions and verified
 * through GET /skills. The usage count reflects the matching worklog tags, and the
 * uncurated tag never appears as a skill (no auto-promotion). Reorder in SkillsView
 * is a drag-only affordance (excluded from e2e per the flaky-flow policy), so the
 * reorder outcome is asserted at the POST /skills/reorder boundary the drag invokes.
 */
test("curate skills through the browser; usage derives from tags and tags do not auto-promote", async ({
  page,
}) => {
  await registerAndOnboard(page);

  // Two entries tagged with the skill name drive a usage count of 2; a third
  // entry carries an uncurated tag that must never become a skill on its own.
  const built = await createWorklog(page.request, {
    title: "Built the type system",
    entryDate: "2026-02-10",
  });
  const refactored = await createWorklog(page.request, {
    title: "Refactored the types",
    entryDate: "2026-03-04",
  });
  const resolver = await createWorklog(page.request, {
    title: "Wrote a GraphQL resolver",
    entryDate: "2026-03-18",
  });
  await addWorklogTag(page.request, built.id, MATCHED_SKILL);
  await addWorklogTag(page.request, refactored.id, MATCHED_SKILL);
  await addWorklogTag(page.request, resolver.id, UNCURATED_TAG);

  // A library bullet framing the tagged entry represents the library-layer corpus
  // that shares the term. Bullets carry no tags in the current backend, so only
  // the worklog tags feed the derived usage count (see repository usage_counts).
  await createBullet(page.request, "Owned the TypeScript type system", {
    worklogIds: [built.id],
  });

  const skillRow = (name: string) => page.getByRole("listitem").filter({ hasText: name });

  await page.goto("/profile/skills");

  // No auto-promotion: tags already exist on the worklog, yet the curated list is
  // empty until a skill is added explicitly.
  await expect(page.getByText("No skills yet.", { exact: false })).toBeVisible();
  expect(await listSkills(page.request)).toEqual([]);

  // Add the matched skill through the form; its derived usage count reflects the
  // two worklog entries tagged with its name.
  await page.getByRole("textbox", { name: "New skill" }).fill(MATCHED_SKILL);
  await page.getByRole("button", { name: "Add" }).click();
  const matchedRow = skillRow(MATCHED_SKILL);
  await expect(matchedRow).toBeVisible();
  await expect(matchedRow.getByText("used in 2", { exact: true })).toBeVisible();

  // Add two more skills to rename and archive.
  await page.getByRole("textbox", { name: "New skill" }).fill("Docker");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(skillRow("Docker")).toBeVisible();

  await page.getByRole("textbox", { name: "New skill" }).fill("Redis");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(skillRow("Redis")).toBeVisible();

  // Rename Docker to Kubernetes through the row's inline edit control.
  const dockerRow = skillRow("Docker");
  await dockerRow.hover();
  await dockerRow.getByRole("button", { name: "Rename Docker" }).click();
  await page.getByRole("textbox", { name: "Rename Docker" }).fill("Kubernetes");
  await page.getByRole("button", { name: "Save name" }).click();
  await expect(skillRow("Kubernetes")).toBeVisible();
  await expect(skillRow("Docker")).toHaveCount(0);

  // Archive Redis through its row control; it drops from the active list.
  const redisRow = skillRow("Redis");
  await redisRow.hover();
  await redisRow.getByRole("button", { name: "Archive Redis" }).click();
  await expect(skillRow("Redis")).toHaveCount(0);

  // The browser interactions persisted: GET /skills returns the two active skills
  // with the matched usage count, no archived Redis, no renamed-away Docker, and
  // crucially no skill named after the uncurated tag.
  await expect
    .poll(async () =>
      (await listSkills(page.request)).map((skill) => ({
        name: skill.name,
        usage: skill.usage_count,
      })),
    )
    .toEqual([
      { name: MATCHED_SKILL, usage: 2 },
      { name: "Kubernetes", usage: 0 },
    ]);

  const active = await listSkills(page.request);
  expect(active.map((skill) => skill.name)).not.toContain(UNCURATED_TAG);
  expect(active.map((skill) => skill.name)).not.toContain("Docker");
  expect(active.map((skill) => skill.name)).not.toContain("Redis");

  // Reorder is drag-only in SkillsView (a flaky flow excluded from e2e), so assert
  // the outcome at the POST /skills/reorder boundary the drag invokes rather than
  // performing a browser drag. Reversing the order flips the persisted sort_order.
  const matched = active.find((skill) => skill.name === MATCHED_SKILL);
  const kubernetes = active.find((skill) => skill.name === "Kubernetes");
  expect(matched && kubernetes, "both active skills should be present before reorder").toBeTruthy();

  const reordered = await page.request.post("/skills/reorder", {
    data: { skill_ids: [kubernetes!.id, matched!.id] },
  });
  expect(reordered.ok(), await bodyText(reordered)).toBeTruthy();
  const reorderedList = (await reordered.json()) as SkillWire[];
  expect(reorderedList.map((skill) => [skill.name, skill.sort_order])).toEqual([
    ["Kubernetes", 0],
    [MATCHED_SKILL, 1],
  ]);

  // The new order persists: a fresh read returns Kubernetes ahead of the matched skill.
  const afterReorder = await listSkills(page.request);
  expect(afterReorder.map((skill) => skill.name)).toEqual(["Kubernetes", MATCHED_SKILL]);
});
