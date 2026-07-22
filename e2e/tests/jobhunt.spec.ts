import { expect, test } from "@playwright/test";

import {
  assertPdfSelectableText,
  createBullet,
  createLivingResume,
  placeBulletViaApi,
  registerAndOnboard,
  seedResumeSection,
  updateBullet,
} from "../harness/support";

const BULLET_TEXT = "Owned the platform migration end to end";

/**
 * Anchor flow 3 — JOB HUNTING. Create a job application, fork a living resume into
 * a tailored application draft, see the live PDF preview, export the ATS PDF (a
 * stored PDF with selectable text), then mark the application submitted, which
 * finalizes the resume read-only. A later library edit never changes the frozen
 * resume.
 */
test("create application, fork, preview, export, and finalize on submit", async ({ page }) => {
  await registerAndOnboard(page);
  const bullet = await createBullet(page.request, BULLET_TEXT);
  const living = await createLivingResume(page.request, "Base Resume");
  const { sectionId } = await seedResumeSection(page.request, living);
  await placeBulletViaApi(page.request, living, sectionId, bullet.id);

  // Create the job application.
  await page.goto("/applications");
  await page.getByRole("button", { name: /New application/ }).click();
  const newApp = page.getByRole("dialog", { name: "Add a job application" });
  await newApp.getByLabel("Company").fill("Hooli");
  await newApp.getByLabel("Role title").fill("Principal Engineer");
  await newApp.getByRole("button", { name: "Add application" }).click();

  // Fork a living resume into the application's tailored draft.
  await page.getByRole("button", { name: "Create resume" }).click();
  const fork = page.getByRole("dialog", { name: "Create the application resume" });
  await fork.getByRole("combobox").selectOption({ label: "Base Resume" });
  await fork.getByRole("button", { name: "Create resume" }).click();
  await expect(page).toHaveURL(/\/resumes\/\d+$/);

  // The live PDF preview renders (no error state).
  const preview = page.getByRole("complementary", { name: "Resume preview" });
  await expect(preview.getByText("Click to enlarge")).toBeVisible();

  // Export the ATS PDF: a stored, presigned download that is a real PDF with
  // selectable text.
  await page.getByRole("button", { name: "Export" }).click();
  const downloadLink = page.getByRole("link", { name: "Download exported PDF" });
  await expect(downloadLink).toBeVisible();
  const href = await downloadLink.getAttribute("href");
  expect(href).toBeTruthy();
  const download = await page.request.get(href as string);
  expect(download.ok()).toBeTruthy();
  assertPdfSelectableText(Buffer.from(await download.body()), "platform migration");

  // Mark the application submitted -> finalizes the linked resume.
  await page.goto("/applications");
  await page.getByRole("button", { name: "Mark submitted" }).click();
  const submit = page.getByRole("dialog", { name: "Mark this application submitted?" });
  await submit.getByRole("button", { name: "Mark submitted" }).click();
  await expect(submit).toBeHidden();
  await expect(page.getByText("Submitted")).toBeVisible();

  // The finalized resume is read-only: items render as static text, not editable.
  await page.getByRole("link", { name: /Hooli/ }).click();
  await expect(page).toHaveURL(/\/resumes\/\d+$/);
  await expect(page.getByText(BULLET_TEXT)).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Bullet text" })).toHaveCount(0);

  // A later library edit does not change the frozen resume.
  await updateBullet(page.request, bullet.id, "EDITED after finalize");
  await page.reload();
  await expect(page.getByText(BULLET_TEXT)).toBeVisible();
  await expect(page.getByText("EDITED after finalize")).toHaveCount(0);
});
