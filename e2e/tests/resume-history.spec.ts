import { expect, test } from "@playwright/test";

import {
  createApplication,
  createApplicationResume,
  createBullet,
  createLivingResume,
  exportResumeViaApi,
  fetchPublishedVersions,
  fetchVersionPdf,
  finalizeResumeViaApi,
  pdfToText,
  placeBulletViaApi,
  registerAndOnboard,
  seedResumeSection,
  updateBullet,
} from "../harness/support";

const HISTORY_BULLET = "Shipped the search relevance rework end to end";
const LATER_BULLET = "Cut onboarding drop-off by redesigning the first-run flow";
const EDITED_TEXT = "REWRITTEN library text after the version was published";
const APP_BULLET = "Drove the billing platform re-architecture across three teams";

/**
 * Follow-up #1: view a published version read-only. Export a living resume twice
 * (each export stores a PDF in R2/MinIO under its revision), then open the editor's
 * History control: it lists the published versions newest-first, opens the selected
 * one as a read-only PDF fetched straight from the presigned R2 URL, and never
 * leaks the object key. A later everywhere library edit leaves an already-published
 * version byte-identical (the US-REV-03 freeze guarantee).
 */
test("History lists published versions newest-first, views one read-only, and freezes it", async ({
  page,
}) => {
  await registerAndOnboard(page);
  const bullet = await createBullet(page.request, HISTORY_BULLET);
  const resumeId = await createLivingResume(page.request, "History resume");
  const { sectionId } = await seedResumeSection(page.request, resumeId);
  await placeBulletViaApi(page.request, resumeId, sectionId, bullet.id);

  // Export once through the editor (the P0 export flow): a stored PDF surfaced via a
  // presigned download link. This records the first published version.
  await page.goto(`/resumes/${resumeId}`);
  const preview = page.getByRole("complementary", { name: "Resume preview" });
  await expect(preview.getByText("Click to enlarge")).toBeVisible();
  await page.getByRole("button", { name: "Export" }).click();
  await expect(page.getByRole("link", { name: "Download exported PDF" })).toBeVisible();

  // Add a bullet (advancing the revision) and export again: a second, newer version.
  const laterBullet = await createBullet(page.request, LATER_BULLET);
  await placeBulletViaApi(page.request, resumeId, sectionId, laterBullet.id);
  const second = await exportResumeViaApi(page.request, resumeId);

  // The list is newest-first and carries only the revision number and timestamp: the
  // R2 object key never appears on the wire (neither in the list nor the URL response).
  const listed = await fetchPublishedVersions(page.request, resumeId);
  expect(listed.versions).toHaveLength(2);
  const [newest, older] = listed.versions;
  expect(newest.revision_no).toBe(second.revision);
  expect(newest.revision_no).toBeGreaterThan(older.revision_no);
  for (const version of listed.versions) {
    expect(Object.keys(version).sort()).toEqual(["created_at", "revision_no"]);
  }
  const olderUrl = await fetchVersionPdf(page.request, resumeId, older.revision_no);
  expect(Object.keys(olderUrl).sort()).toEqual(["download_url", "resume_id", "revision_no"]);

  // The stored bytes of the older version have selectable text with its bullet.
  const before = await page.request.get(olderUrl.download_url);
  expect(before.ok(), "presigned R2 fetch of the older version").toBeTruthy();
  const beforeBytes = Buffer.from(await before.body());
  expect(pdfToText(beforeBytes)).toContain(HISTORY_BULLET);

  // Open History: two rows, newest-first, and no edit affordance for a past version.
  await page.getByRole("button", { name: "History" }).click();
  const dialog = page.getByRole("dialog", { name: "Version history" });
  await expect(dialog).toBeVisible();
  const rows = dialog.getByRole("button", { name: /Revision \d+/ });
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toContainText(`Revision ${newest.revision_no}`);
  await expect(rows.nth(1)).toContainText(`Revision ${older.revision_no}`);
  await expect(dialog.getByRole("textbox")).toHaveCount(0);

  // Selecting the newest row fetches the presigned R2 PDF and renders it read-only.
  await rows.nth(0).click();
  await expect(
    dialog.locator(`canvas[aria-label="Revision ${newest.revision_no} PDF"]`),
  ).toBeVisible();
  await expect(dialog.getByText("This version's PDF is unavailable.")).toHaveCount(0);
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toBeHidden();

  // Freeze guarantee: edit the bullet everywhere, then the published version's stored
  // PDF is byte-identical and still shows the old text, never the later edit.
  await updateBullet(page.request, bullet.id, EDITED_TEXT);
  const reminted = await fetchVersionPdf(page.request, resumeId, older.revision_no);
  const after = await page.request.get(reminted.download_url);
  expect(after.ok()).toBeTruthy();
  const afterBytes = Buffer.from(await after.body());
  expect(afterBytes.equals(beforeBytes)).toBe(true);
  const afterText = pdfToText(afterBytes);
  expect(afterText).toContain(HISTORY_BULLET);
  expect(afterText).not.toContain(EDITED_TEXT);

  // Re-opening the same version after the edit still renders it read-only.
  await page.getByRole("button", { name: "History" }).click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: new RegExp(`Revision ${older.revision_no}`) }).click();
  await expect(
    dialog.locator(`canvas[aria-label="Revision ${older.revision_no} PDF"]`),
  ).toBeVisible();
});

/**
 * An application resume's finalize PDF is a published version too: it appears in
 * History alongside any export versions, and opens read-only from R2 with selectable
 * text.
 */
test("an application resume's finalize PDF appears in History with export versions", async ({
  page,
}) => {
  await registerAndOnboard(page);
  const bullet = await createBullet(page.request, APP_BULLET);
  const base = await createLivingResume(page.request, "Application base");
  const { sectionId } = await seedResumeSection(page.request, base);
  await placeBulletViaApi(page.request, base, sectionId, bullet.id);

  // Fork the base into an application draft, export it (an export version), then
  // finalize it (a finalize version). Both are published versions of the same resume.
  const application = await createApplication(page.request, "Initech", "Staff Engineer");
  const appResumeId = await createApplicationResume(page.request, {
    fromResumeId: base,
    jobApplicationId: application.id,
  });
  const exported = await exportResumeViaApi(page.request, appResumeId);
  const finalized = await finalizeResumeViaApi(page.request, appResumeId);

  const listed = await fetchPublishedVersions(page.request, appResumeId);
  expect(listed.versions).toHaveLength(2);
  const [newest, older] = listed.versions;
  expect(newest.revision_no).toBe(finalized.revisionNo);
  expect(older.revision_no).toBe(exported.revision);
  expect(newest.revision_no).toBeGreaterThan(older.revision_no);

  // The finalize version opens read-only from R2 with selectable text.
  const finalizeUrl = await fetchVersionPdf(page.request, appResumeId, finalized.revisionNo);
  const finalizePdf = await page.request.get(finalizeUrl.download_url);
  expect(finalizePdf.ok()).toBeTruthy();
  expect(pdfToText(Buffer.from(await finalizePdf.body()))).toContain(APP_BULLET);

  // History on the (now finalized, read-only) resume lists the finalize version
  // newest-first alongside the export version, and opens it read-only.
  await page.goto(`/resumes/${appResumeId}`);
  await page.getByRole("button", { name: "History" }).click();
  const dialog = page.getByRole("dialog", { name: "Version history" });
  await expect(dialog).toBeVisible();
  const rows = dialog.getByRole("button", { name: /Revision \d+/ });
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toContainText(`Revision ${finalized.revisionNo}`);
  await rows.nth(0).click();
  await expect(
    dialog.locator(`canvas[aria-label="Revision ${finalized.revisionNo} PDF"]`),
  ).toBeVisible();
  await expect(dialog.getByText("This version's PDF is unavailable.")).toHaveCount(0);
});
