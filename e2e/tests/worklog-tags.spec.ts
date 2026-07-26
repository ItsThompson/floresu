import { expect, test, type APIRequestContext, type Locator } from "@playwright/test";

import { bodyText, createWorklog, registerAndOnboard } from "../harness/support";

const SHARED_TAG = "backend";
const OTHER_TAG = "api";

/** Add one tag label to an entry through the real POST /worklog/{id}/tags add action. */
async function addTag(request: APIRequestContext, worklogId: number, label: string): Promise<void> {
  const response = await request.post(`/worklog/${worklogId}/tags`, {
    data: { label, action: "add" },
  });
  expect(response.ok(), await bodyText(response)).toBeTruthy();
}

/** GET a route and parse it, asserting ok with the body as the failure message. */
async function getJson<T>(request: APIRequestContext, path: string): Promise<T> {
  const response = await request.get(path);
  expect(response.ok(), await bodyText(response)).toBeTruthy();
  return (await response.json()) as T;
}

/**
 * C5: worklog tag remove and deterministic color. Two entries share a tag; one
 * also carries a second, distinct tag. Removing the shared tag from one entry
 * (through its edit control) drops only that entry's edge: the other entry keeps
 * it and it stays listed globally by GET /worklog/tags. A tag's rendered color is
 * a deterministic function of its label, so the shared tag is the same color in
 * both entries, while the distinct tag differs, asserted without a hex literal.
 */
test("remove a shared worklog tag from one entry; it persists globally and its color is deterministic", async ({
  page,
}) => {
  await registerAndOnboard(page);

  const entryA = await createWorklog(page.request, {
    title: "Refined the auth service",
    entryDate: "2026-03-05",
  });
  const entryB = await createWorklog(page.request, {
    title: "Tuned the rate limiter",
    entryDate: "2026-04-02",
  });

  // Both entries share SHARED_TAG; entry A also carries OTHER_TAG, a distinct
  // label whose color must differ, proving color is derived from the string.
  await addTag(page.request, entryA.id, SHARED_TAG);
  await addTag(page.request, entryA.id, OTHER_TAG);
  await addTag(page.request, entryB.id, SHARED_TAG);

  await page.goto("/worklog");

  const rowA = page.getByRole("listitem").filter({ hasText: "Refined the auth service" });
  const rowB = page.getByRole("listitem").filter({ hasText: "Tuned the rate limiter" });

  const sharedInA = rowA.getByText(`#${SHARED_TAG}`, { exact: true });
  const sharedInB = rowB.getByText(`#${SHARED_TAG}`, { exact: true });
  await expect(sharedInA).toBeVisible();
  await expect(sharedInB).toBeVisible();

  // Compare the rendered color, not a palette hex: the same tag must be identical
  // wherever it appears, and a different tag must differ.
  const readColor = (locator: Locator) =>
    locator.evaluate((element) => getComputedStyle(element).color);
  const sharedColorA = await readColor(sharedInA);
  const sharedColorB = await readColor(sharedInB);
  const otherColorA = await readColor(rowA.getByText(`#${OTHER_TAG}`, { exact: true }));

  expect(sharedColorA).toBe(sharedColorB);
  expect(sharedColorA).not.toBe(otherColorA);

  // Remove the shared tag from entry A through its edit control (the pill's ✕).
  await page.getByRole("button", { name: "Actions for Refined the auth service" }).click();
  await page.getByRole("button", { name: "Edit" }).click();
  const editForm = page.getByRole("form", { name: "Edit entry" });
  await editForm.getByRole("button", { name: `Remove tag ${SHARED_TAG}` }).click();
  await editForm.getByRole("button", { name: "Save entry" }).click();

  // The pill is gone from entry A but remains on entry B (and A keeps its own tag).
  await expect(rowA.getByText(`#${SHARED_TAG}`, { exact: true })).toHaveCount(0);
  await expect(rowA.getByText(`#${OTHER_TAG}`, { exact: true })).toBeVisible();
  await expect(rowB.getByText(`#${SHARED_TAG}`, { exact: true })).toBeVisible();

  // The API confirms the edge was dropped only for entry A.
  const summaries = await getJson<{ id: number; tags: string[] }[]>(page.request, "/worklog");
  const readA = summaries.find((summary) => summary.id === entryA.id);
  const readB = summaries.find((summary) => summary.id === entryB.id);
  expect(readA?.tags).not.toContain(SHARED_TAG);
  expect(readA?.tags).toContain(OTHER_TAG);
  expect(readB?.tags).toContain(SHARED_TAG);

  // The tag survives globally because entry B still uses it.
  const globalTags = await getJson<{ label: string }[]>(page.request, "/worklog/tags");
  expect(globalTags.map((tag) => tag.label)).toContain(SHARED_TAG);
});
