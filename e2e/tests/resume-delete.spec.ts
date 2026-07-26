import { expect, test, type Locator, type Page } from "@playwright/test";

import {
  bodyText,
  createApplication,
  createApplicationResume,
  createBullet,
  createLivingResume,
  fetchPublishedVersions,
  fetchVersionPdf,
  finalizeResumeViaApi,
  pdfToText,
  placeBulletViaApi,
  registerAndOnboard,
  seedResumeSection,
} from "../harness/support";

const RETAINED_BULLET = "Led the storage-retention rework that outlives its resume";

/**
 * Permanent resume delete, web-only and confirm-gated. The DELETE route lives on
 * the external app alone (the internal app has no delete route, asserted in
 * agent-boundary), so both cases drive the web app: click Delete on the resumes
 * list, satisfy the destructive confirm gate, and confirm the resume leaves the
 * list and its read reports gone.
 *
 * The finalized case also pins the retention contract: deleting a resume removes
 * the resume and its revision rows (they cascade), so the resume-scoped revision
 * route no longer resolves, but the finalized PDF object itself is retained in
 * storage: a URL minted before the delete still resolves to the byte-identical
 * frozen PDF.
 */

/** Drive the confirm-gated permanent delete for one resume row through the browser. */
async function deleteResumeViaWeb(page: Page, row: Locator): Promise<void> {
  await row.getByRole("button", { name: "Delete" }).click();
  const confirm = page.getByRole("dialog", { name: "Delete resume permanently?" });
  await expect(confirm).toBeVisible();
  // The gate states the action is permanent and irreversible before it can fire.
  await expect(confirm.getByText(/will be permanently deleted\. This cannot be undone\./)).toBeVisible();
  const confirmButton = confirm.getByRole("button", { name: "Delete permanently" });
  await expect(confirmButton).toBeVisible();
  await confirmButton.click();
  await expect(confirm).toBeHidden();
}

test("permanently deletes a living resume through the confirm-gated web flow", async ({ page }) => {
  await registerAndOnboard(page);
  const livingId = await createLivingResume(page.request, "Living resume to delete");

  await page.goto("/resumes");
  const row = page.getByRole("listitem").filter({ hasText: "Living resume to delete" });
  await expect(row).toBeVisible();

  await deleteResumeViaWeb(page, row);

  // It leaves the resumes list and its read reports it gone.
  await expect(row).toHaveCount(0);
  const gone = await page.request.get(`/resumes/${livingId}`);
  expect(gone.status()).toBe(404);
});

test("deletes a finalized resume but retains its stored PDF per retention", async ({ page }) => {
  await registerAndOnboard(page);

  // Seed a finalized application resume whose finalize stored a PDF with selectable
  // text: fork a living base carrying one bullet, then finalize the fork.
  const bullet = await createBullet(page.request, RETAINED_BULLET);
  const base = await createLivingResume(page.request, "Finalized base resume");
  const { sectionId } = await seedResumeSection(page.request, base);
  await placeBulletViaApi(page.request, base, sectionId, bullet.id);
  const application = await createApplication(page.request, "Retention Co", "Staff Engineer");
  const finalizedId = await createApplicationResume(page.request, {
    fromResumeId: base,
    jobApplicationId: application.id,
  });
  const finalized = await finalizeResumeViaApi(page.request, finalizedId);

  // Capture the frozen version's stored PDF before the delete: it lists as a
  // published version and its presigned URL resolves to a PDF carrying the bullet.
  const versions = await fetchPublishedVersions(page.request, finalizedId);
  expect(versions.versions.map((version) => version.revision_no)).toContain(finalized.revisionNo);
  const frozen = await fetchVersionPdf(page.request, finalizedId, finalized.revisionNo);
  const before = await page.request.get(frozen.download_url);
  expect(before.ok(), await bodyText(before)).toBeTruthy();
  const beforeBytes = Buffer.from(await before.body());
  expect(pdfToText(beforeBytes)).toContain(RETAINED_BULLET);

  // Delete the finalized resume through the confirm-gated web flow. Its title is
  // inherited from the base, so select the row by its editor link, not its text.
  await page.goto("/resumes");
  const finalizedRow = page
    .getByRole("listitem")
    .filter({ has: page.locator(`a[href="/resumes/${finalizedId}"]`) });
  await expect(finalizedRow).toBeVisible();
  await deleteResumeViaWeb(page, finalizedRow);
  await expect(finalizedRow).toHaveCount(0);

  // The resume itself is gone.
  const gone = await page.request.get(`/resumes/${finalizedId}`);
  expect(gone.status()).toBe(404);

  // The revision rows cascade with the resume, so the resume-scoped revision route
  // no longer resolves.
  const revisionRoute = await page.request.get(
    `/resumes/${finalizedId}/revisions/${finalized.revisionNo}/pdf`,
  );
  expect(revisionRoute.status()).toBe(404);

  // Retention: the finalized PDF object is kept in storage. The URL minted before
  // the delete still resolves to the byte-identical frozen PDF.
  const after = await page.request.get(frozen.download_url);
  expect(after.ok(), await bodyText(after)).toBeTruthy();
  const afterBytes = Buffer.from(await after.body());
  expect(afterBytes.equals(beforeBytes)).toBe(true);
  expect(pdfToText(afterBytes)).toContain(RETAINED_BULLET);
});
