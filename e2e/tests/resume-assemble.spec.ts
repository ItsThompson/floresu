import { expect, test } from "@playwright/test";

import {
  createBullet,
  createLivingResume,
  placeBulletViaApi,
  registerAndOnboard,
  seedResumeSection,
} from "../harness/support";

/**
 * Assemble a living resume and exercise copy-on-write. A bullet used in two
 * resumes prompts the scope dialog on edit: "Only this resume" forks a local copy
 * and leaves the other resume's canonical text unchanged, while "Everywhere"
 * rewrites the shared bullet for both. A forked local item can then be promoted
 * back into the library.
 */
test("copy-on-write scope: fork this resume, edit everywhere, and promote", async ({ page }) => {
  await registerAndOnboard(page);
  const alpha = await createBullet(page.request, "Alpha bullet original");
  const beta = await createBullet(page.request, "Beta bullet original");

  const living = await createLivingResume(page.request, "Living One");
  const target = await createLivingResume(page.request, "Living Two");
  const { sectionId: livingSection } = await seedResumeSection(page.request, living);
  await seedResumeSection(page.request, target);

  // The first resume references both bullets (via the item endpoint, so the
  // resume-reference count is maintained).
  await placeBulletViaApi(page.request, living, livingSection, alpha.id);
  await placeBulletViaApi(page.request, living, livingSection, beta.id);

  // Assemble the second resume in the browser: pull the same two bullets from the
  // library. Each is now used in two resumes.
  await page.goto(`/resumes/${target}`);
  await pullFromLibrary(page, "Alpha bullet original");
  await pullFromLibrary(page, "Beta bullet original");

  const rows = page.getByRole("textbox", { name: "Bullet text" });
  await expect(rows).toHaveCount(2);

  // Edit the first bullet -> scope dialog -> "Only this resume" forks a local copy.
  await rows.nth(0).fill("Alpha bullet forked here only");
  await rows.nth(0).blur();
  const scope = page.getByRole("dialog", { name: /used in 2 resumes/ });
  await expect(scope).toBeVisible();
  await scope.getByRole("radio", { name: /Only this resume/ }).check();
  await scope.getByRole("button", { name: "Apply" }).click();
  await expect(scope).toBeHidden();
  await expect(rows.nth(0)).toHaveValue("Alpha bullet forked here only");

  // Edit the second bullet -> scope dialog -> "Everywhere" rewrites the canonical.
  await rows.nth(1).fill("Beta bullet changed everywhere");
  await rows.nth(1).blur();
  const scope2 = page.getByRole("dialog", { name: /used in 2 resumes/ });
  await expect(scope2).toBeVisible();
  await scope2.getByRole("radio", { name: /Everywhere/ }).check();
  await scope2.getByRole("button", { name: "Apply" }).click();
  await expect(scope2).toBeHidden();

  // Promote the forked local item back into the library.
  await page.getByRole("button", { name: "Promote" }).click();
  await expect(page.getByRole("button", { name: "Promote" })).toBeHidden();

  // The other resume is unchanged by "only this resume" but reflects "everywhere".
  await page.goto(`/resumes/${living}`);
  const livingRows = page.getByRole("textbox", { name: "Bullet text" });
  await expect(livingRows.nth(0)).toHaveValue("Alpha bullet original");
  await expect(livingRows.nth(1)).toHaveValue("Beta bullet changed everywhere");

  // The promoted fork is now a canonical library bullet.
  const bullets = (await (await page.request.get("/bullets")).json()) as { text: string }[];
  expect(bullets.map((bullet) => bullet.text)).toContain("Alpha bullet forked here only");
});

/** Open a section's library picker and add the bullet whose text matches. */
async function pullFromLibrary(page: import("@playwright/test").Page, bulletText: string) {
  await page.getByRole("button", { name: /pull from library/ }).click();
  const picker = page.getByRole("dialog", { name: "Pull from library" });
  await picker.getByRole("button", { name: new RegExp(bulletText) }).click();
  await expect(picker).toBeHidden();
}
