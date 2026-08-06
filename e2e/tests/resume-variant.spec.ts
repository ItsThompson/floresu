import { expect, test, type APIRequestContext } from "@playwright/test";

import { bodyText, createLivingResume, createVariant, registerAndOnboard } from "../harness/support";

/**
 * The identity variant selector on a living resume's header. A living resume
 * resolves its contact facts from the variant its header references, so switching
 * the variant re-points the header and changes what the next preview renders. This
 * asserts the switch through the resume document (`GET /resumes/{id}`), not the
 * rendered pixels: the preview request body carries no variant (the server resolves
 * it from the stored document), so the document is the authoritative surface.
 */
test("switches the resume header identity variant through the selector", async ({ page }) => {
  await registerAndOnboard(page);

  // The first variant is server-forced default; the second is a distinct,
  // non-default identity the user can switch to.
  const primary = await createVariant(page.request, { label: "Primary identity", fullName: "Ada Lovelace" });
  const recruiting = await createVariant(page.request, {
    label: "Recruiting focus",
    fullName: "Grace Hopper",
  });
  expect(primary.isDefault).toBe(true);
  expect(recruiting.isDefault).toBe(false);

  // Seed the resume so its header references the default variant, the configured
  // state in which the header selector opens on the default variant.
  const resumeId = await createLivingResume(page.request, "Variant Selector Resume");
  await pointHeaderAtVariant(page.request, resumeId, primary.id);

  await page.goto(`/resumes/${resumeId}`);

  // On open the selector defaults to the default variant, marked "(default)".
  const selector = page.getByLabel("Identity variant");
  await expect(selector).toHaveValue(String(primary.id));
  await expect(selector.locator("option:checked")).toContainText("(default)");

  // Switch to the second, non-default variant.
  await selector.selectOption(String(recruiting.id));
  await expect(selector).toHaveValue(String(recruiting.id));
  await expect(selector.locator("option:checked")).not.toContainText("(default)");

  // The switch persists on the resume document: the header now references the chosen
  // variant, which is what the next preview resolves its contact facts from.
  await expect
    .poll(async () => {
      const response = await page.request.get(`/resumes/${resumeId}`);
      expect(response.ok(), await bodyText(response)).toBeTruthy();
      const record = (await response.json()) as {
        document: { header: { identity_variant_id: number | null } };
      };
      return record.document.header.identity_variant_id;
    })
    .toBe(recruiting.id);
});

/** Point a living resume's header at a variant via the full-document PUT (If-Match guarded). */
async function pointHeaderAtVariant(
  request: APIRequestContext,
  resumeId: number,
  variantId: number,
): Promise<void> {
  const current = await request.get(`/resumes/${resumeId}`);
  expect(current.ok(), await bodyText(current)).toBeTruthy();
  const record = (await current.json()) as {
    revision: number;
    title: string;
    document: { template_id: string; sections: unknown[] };
  };
  const updated = await request.put(`/resumes/${resumeId}`, {
    headers: { "If-Match": String(record.revision) },
    data: {
      title: record.title,
      template_id: record.document.template_id,
      header: { identity_variant_id: variantId },
      sections: record.document.sections,
    },
  });
  expect(updated.ok(), await bodyText(updated)).toBeTruthy();
}
