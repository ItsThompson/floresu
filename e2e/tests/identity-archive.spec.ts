import { expect, test, type Page } from "@playwright/test";

import { createLivingResume, registerAndOnboard } from "../harness/support";

/**
 * Archive an identity variant that a living resume references. The archive is not
 * silent: because a living resume points at the variant, the identities page opens
 * a replacement prompt. Choosing a replacement re-points the referencing resume's
 * header to it and archives the original in one atomic backend operation. Reopening
 * the resume shows the replacement selected, never "None selected" (BUG-004).
 */
test("archiving a referenced variant with a replacement re-points the resume", async ({ page }) => {
  await registerAndOnboard(page);

  // The first variant is forced default; the second is what the resume references.
  const primary = await createVariant(page, "Primary");
  const recruiting = await createVariant(page, "Recruiting");

  const resumeId = await createLivingResume(page.request, "Referencing Resume");
  await setResumeVariant(page, resumeId, recruiting.id);

  // Archive the referenced variant from the identities page.
  await page.goto("/profile/identities");
  await page.getByRole("button", { name: "Archive Recruiting" }).click();

  // The replacement prompt appears and states how many resumes reference it.
  const dialog = page.getByRole("dialog", { name: "Pick a replacement variant" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/1 living resume/)).toBeVisible();

  // Choose Primary as the replacement and confirm.
  await dialog.getByLabel("Replacement").selectOption(String(primary.id));
  await dialog.getByRole("button", { name: "Archive and re-point" }).click();

  // The prompt closes and the archived variant leaves the active list.
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "Archive Recruiting" })).toBeHidden();

  // Reopen the resume: its header now resolves to the replacement, not "None selected".
  await page.goto(`/resumes/${resumeId}`);
  await expect(page.getByLabel("Identity variant")).toHaveValue(String(primary.id));
});

/** Create an identity variant through the API; returns its id. */
async function createVariant(page: Page, label: string): Promise<{ id: number }> {
  const response = await page.request.post("/identity-variants", {
    data: { label, full_name: "Ada Lovelace", contact: {}, links: [], is_default: false },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()) as { id: number };
}

/** Point a living resume's header at a variant via the full-document PUT (If-Match guarded). */
async function setResumeVariant(page: Page, resumeId: number, variantId: number): Promise<void> {
  const current = await page.request.get(`/resumes/${resumeId}`);
  expect(current.ok(), await current.text()).toBeTruthy();
  const record = (await current.json()) as {
    revision: number;
    title: string;
    document: { template_id: string; sections: unknown[] };
  };
  const updated = await page.request.put(`/resumes/${resumeId}`, {
    headers: { "If-Match": String(record.revision) },
    data: {
      title: record.title,
      template_id: record.document.template_id,
      header: { identity_variant_id: variantId },
      sections: record.document.sections,
    },
  });
  expect(updated.ok(), await updated.text()).toBeTruthy();
}
