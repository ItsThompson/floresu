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

/**
 * Build a resume from a blank starting point entirely on the web: add the first
 * section with the add-section control (no MCP, no API seed), then reach the
 * section's own add-item controls to pull a library bullet and add an inline one.
 */
test("build a resume from blank on the web: add section, pull a bullet, add inline", async ({
  page,
}) => {
  await registerAndOnboard(page);
  const bullet = await createBullet(page.request, "Cut checkout latency by 40%");
  const resumeId = await createLivingResume(page.request, "From Blank");

  await page.goto(`/resumes/${resumeId}`);

  // A blank resume shows the add-section control, not a dead-end message.
  await expect(page.getByRole("button", { name: "New section", exact: true })).toBeVisible();

  // Add the first section through the web control.
  await page.getByRole("button", { name: "New section", exact: true }).click();
  await page.getByLabel("Section kind").selectOption("work");
  await page.getByLabel("Section title").fill("Experience");
  await page.getByRole("button", { name: "Add section", exact: true }).click();

  // The new section renders without a reload; its add-item controls are reachable.
  await expect(page.getByText("Experience")).toBeVisible();
  await pullFromLibrary(page, "Cut checkout latency by 40%");

  const rows = page.getByRole("textbox", { name: "Bullet text" });
  await expect(rows).toHaveCount(1);

  // Pulling the library bullet raises its used-in count (exercised from the browser).
  const bullets = (await (await page.request.get("/bullets")).json()) as {
    id: number;
    used_in_count: number;
  }[];
  expect(bullets.find((entry) => entry.id === bullet.id)?.used_in_count).toBe(1);

  // Add a net-new inline item into the same section.
  await page.getByRole("button", { name: "new", exact: true }).click();
  await page.getByLabel("New bullet text").fill("Shipped the blank-start flow");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(rows).toHaveCount(2);
});

/** Open a section's library picker and add the bullet whose text matches. */
async function pullFromLibrary(page: import("@playwright/test").Page, bulletText: string) {
  await page.getByRole("button", { name: /pull from library/ }).click();
  const picker = page.getByRole("dialog", { name: "Pull from library" });
  await picker.getByRole("button", { name: new RegExp(bulletText) }).click();
  await expect(picker).toBeHidden();
}
