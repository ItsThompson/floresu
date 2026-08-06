import { expect, test } from "@playwright/test";

import { bodyText, createRole, createWorklog, registerAndOnboard } from "../harness/support";

/**
 * The source detail's contextual worklog side panel. A role's entries appear
 * grouped by month, and an entry added from the panel's quick-add form is
 * pre-attached to that source. The pre-attach is proven through the API (a
 * UI-only attachment check would be flaky), per the cross-flow rule.
 */
test("role detail lists worklog entries by month and pre-attaches a panel-added entry", async ({
  page,
}) => {
  await registerAndOnboard(page);
  const role = await createRole(page.request, "Initech", "Platform Engineer");

  // Two seeded entries in different months, both attached to the role.
  await createWorklog(page.request, {
    title: "Migrated the billing ledger",
    entryDate: "2026-03-12",
    sourceIds: [role.id],
  });
  await createWorklog(page.request, {
    title: "Launched the referral program",
    entryDate: "2026-05-20",
    sourceIds: [role.id],
  });

  // Open the role detail; the contextual worklog panel buckets entries by month.
  await page.goto(`/profile/sources/${role.id}`);
  const panel = page.getByRole("region", { name: "Work log" });
  await expect(panel.getByRole("region", { name: "March 2026" }).getByText("Migrated the billing ledger")).toBeVisible();
  await expect(panel.getByRole("region", { name: "May 2026" }).getByText("Launched the referral program")).toBeVisible();

  // Add an entry from the panel's quick-add form.
  await panel.getByRole("button", { name: "Add entry" }).click();
  const form = panel.getByRole("form", { name: "Add worklog entry" });
  await form.getByLabel("Title").fill("Wrote the incident retro");
  await form.getByLabel("Date").fill("2026-07-08");
  await form.getByRole("button", { name: "Add entry" }).click();

  // The new entry appears in the panel, in its own month bucket.
  await expect(panel.getByRole("region", { name: "July 2026" }).getByText("Wrote the incident retro")).toBeVisible();

  // The panel-added entry is persisted pre-attached to this source: prove via the
  // API, reading the single entry and asserting the source id is on its edges.
  const listed = (await (await page.request.get("/worklog")).json()) as { id: number; title: string }[];
  const created = listed.find((entry) => entry.title === "Wrote the incident retro");
  expect(created, "the panel-added entry should be in the worklog list").toBeTruthy();

  const read = await page.request.get(`/worklog/${created!.id}`);
  expect(read.ok(), await bodyText(read)).toBeTruthy();
  const record = (await read.json()) as { source_ids: number[] };
  expect(record.source_ids).toContain(role.id);
});
