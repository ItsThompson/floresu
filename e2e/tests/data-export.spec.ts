import { expect, test } from "@playwright/test";

import {
  createBullet,
  createRole,
  createWorklog,
  exportData,
  registerAndOnboard,
} from "../harness/support";

/**
 * B1 data export. An account-scoped, full-stack flow: seed a known graph (a
 * role, a worklog entry attached to it, and a bullet linked to both) through the
 * API, trigger the export control on the Settings data surface, and assert the
 * produced archive holds exactly the seeded records. The control is a credentialed
 * `download` link, so clicking it fires a browser download; the archive contents
 * are asserted through `exportData` (an XHR the preview proxy forwards to the
 * backend), following the cross-flow rule to assert persisted state via the API
 * rather than scrape the download UI.
 */

/** The subset of each archive collection this test asserts against. */
interface ArchiveAccount {
  email: string;
}
interface ArchiveSource {
  id: number;
  kind: string;
  display_label: string;
}
interface ArchiveWorklogEntry {
  id: number;
  title: string;
  source_ids: number[];
}
interface ArchiveBullet {
  id: number;
  text: string;
  source_ids: number[];
  worklog_ids: number[];
}

const WORKLOG_TITLE = "Shipped the billing rewrite";
const BULLET_TEXT = "Cut checkout latency by 40%";

test("export from settings produces a downloadable archive of the account's records", async ({
  page,
}) => {
  const { email } = await registerAndOnboard(page);

  // Seed a connected graph so the archive must resolve edges, not just rows.
  const role = await createRole(page.request, "Acme Corp", "Staff Engineer");
  const worklog = await createWorklog(page.request, {
    title: WORKLOG_TITLE,
    entryDate: "2026-02-10",
    sourceIds: [role.id],
  });
  const bullet = await createBullet(page.request, BULLET_TEXT, {
    sourceIds: [role.id],
    worklogIds: [worklog.id],
  });

  // Drive: the export control initiates a browser download.
  await page.goto("/settings/data");
  await expect(page.getByRole("heading", { name: "Export your data" })).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export my data" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename().length).toBeGreaterThan(0);

  // Assert the archive contents match exactly what was seeded, edges included.
  const archive = await exportData(page.request);
  expect((archive.account as ArchiveAccount).email).toBe(email);

  const sources = archive.sources as ArchiveSource[];
  expect(sources).toHaveLength(1);
  expect(sources[0]).toMatchObject({ id: role.id, kind: "role", display_label: role.label });

  const worklogEntries = archive.worklog_entries as ArchiveWorklogEntry[];
  expect(worklogEntries).toHaveLength(1);
  expect(worklogEntries[0]).toMatchObject({
    id: worklog.id,
    title: WORKLOG_TITLE,
    source_ids: [role.id],
  });

  const bullets = archive.bulletpoints as ArchiveBullet[];
  expect(bullets).toHaveLength(1);
  expect(bullets[0]).toMatchObject({
    id: bullet.id,
    text: BULLET_TEXT,
    source_ids: [role.id],
    worklog_ids: [worklog.id],
  });
});
