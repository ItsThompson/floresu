import { expect, test } from "@playwright/test";

import { createWorklog, registerAndOnboard } from "../harness/support";

/**
 * Settings — Archive & Trash and the connected-agents surface. Archiving removes
 * an item from its views; restore returns it; permanent delete is web-only and
 * gated behind an explicit acknowledgement. The connected-agents section renders
 * its empty state before any agent connects.
 */
test("archive restore and web-only permanent delete", async ({ page }) => {
  await registerAndOnboard(page);
  const one = await createWorklog(page.request, { title: "Archived entry one", entryDate: "2026-05-01" });
  const two = await createWorklog(page.request, { title: "Archived entry two", entryDate: "2026-05-02" });
  await page.request.post(`/worklog/${one.id}/archive`);
  await page.request.post(`/worklog/${two.id}/archive`);

  await page.goto("/settings/archive");
  await expect(page.getByRole("heading", { name: "Archive & Trash" })).toBeVisible();
  const item1 = page.getByRole("listitem").filter({ hasText: "Archived entry one" });
  const item2 = page.getByRole("listitem").filter({ hasText: "Archived entry two" });
  await expect(item1).toBeVisible();
  await expect(item2).toBeVisible();

  // Restore returns the item to its active views.
  await item1.getByRole("button", { name: "Restore" }).click();
  await expect(page.getByText("Archived entry one")).toHaveCount(0);
  await page.goto("/worklog");
  await expect(page.getByText("Archived entry one")).toBeVisible();

  // Permanent delete is web-only and gated behind an acknowledgement.
  await page.goto("/settings/archive");
  await page
    .getByRole("listitem")
    .filter({ hasText: "Archived entry two" })
    .getByRole("button", { name: "Delete" })
    .click();
  const confirm = page.getByRole("alertdialog", { name: "Permanently delete this item?" });
  await confirm.getByRole("checkbox").check();
  await confirm.getByRole("button", { name: "Delete permanently" }).click();
  await expect(page.getByText("Archived entry two")).toHaveCount(0);

  // The connected-agents surface renders its empty state.
  await page.goto("/settings/agents");
  await expect(page.getByRole("heading", { name: "Connect an agent" })).toBeVisible();
  await expect(page.getByText("No agents are connected yet.")).toBeVisible();
});
