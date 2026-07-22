import { expect, test } from "@playwright/test";

import { createRole, registerAndOnboard } from "../harness/support";

/**
 * Anchor flow 2 — UPDATE THE WORKLOG. Add a worklog entry with a tag and a source
 * attachment, edit it, then create a library bullet linked to that source and
 * entry. The Library groups the bullet under its source and shows the correct
 * usage badge.
 */
test("add and edit worklog entries, then create a linked library bullet", async ({ page }) => {
  await registerAndOnboard(page);
  const role = await createRole(page.request, "Globex", "Senior Engineer");

  // Add an entry: title, date, a tag, and the source attachment.
  await page.goto("/worklog");
  await page.getByRole("button", { name: /Add entry/ }).first().click();
  const form = page.getByRole("form", { name: "Add entry" });
  await form.getByLabel("Title").fill("Led the checkout latency project");
  await form.getByLabel("Date").fill("2026-03-01");
  await form.getByLabel("Add a tag").fill("performance");
  await form.getByRole("button", { name: "Add" }).click();
  await expect(form.getByText("performance")).toBeVisible();
  await form.getByRole("checkbox", { name: role.label }).check();
  await form.getByRole("button", { name: "Save entry" }).click();

  const entry = page.getByText("Led the checkout latency project");
  await expect(entry).toBeVisible();

  // Edit the entry (via its overflow menu): refine the title.
  await page.getByRole("button", { name: "Actions for Led the checkout latency project" }).click();
  await page.getByRole("button", { name: "Edit" }).click();
  const editForm = page.getByRole("form", { name: "Edit entry" });
  await editForm.getByLabel("Title").fill("Led the checkout latency initiative");
  await editForm.getByRole("button", { name: "Save entry" }).click();
  await expect(page.getByText("Led the checkout latency initiative")).toBeVisible();

  // Create a library bullet linked to the source and the worklog entry.
  await page.goto("/library");
  await page.getByRole("button", { name: "New bullet" }).click();
  const bulletForm = page.getByRole("form", { name: "New bullet" });
  await bulletForm
    .getByLabel("Statement")
    .fill("Cut p95 checkout latency 40% by parallelizing pricing calls");
  await bulletForm.getByRole("checkbox", { name: role.label }).check();
  await bulletForm.getByRole("checkbox", { name: /Led the checkout latency initiative/ }).check();
  await bulletForm.getByRole("button", { name: "Save bullet" }).click();

  // The bullet is grouped under its source heading, and unused (no resume refs yet).
  await expect(page.getByText("Cut p95 checkout latency 40%")).toBeVisible();
  await expect(page.getByRole("heading", { name: new RegExp("Globex — Senior Engineer") })).toBeVisible();
  await expect(page.getByText("Unused").first()).toBeVisible();
});
