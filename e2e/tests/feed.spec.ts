import { expect, test } from "@playwright/test";

import { createWorklog, registerAndOnboard } from "../harness/support";

/**
 * The live SSE activity feed reflects a human action. With Home open and its feed
 * stream connected, a write performed through the API pushes a single event to
 * the feed with no duplicate, and a reload (history replay) still shows exactly
 * one row.
 */
test("the activity feed reflects a human action live", async ({ page }) => {
  await registerAndOnboard(page);

  await page.goto("/");
  const feed = page.getByRole("region", { name: "Activity feed" });
  await expect(feed.getByText("No activity yet.")).toBeVisible();

  // A human write while the feed stream is open pushes one event over SSE.
  await createWorklog(page.request, { title: "Live feed entry", entryDate: "2026-04-01" });

  await expect(feed.getByRole("listitem")).toHaveCount(1);
  await expect(feed.getByText("You", { exact: true })).toBeVisible();
  await expect(feed.getByText(/created/)).toBeVisible();

  // History replay on reload shows the same single row, not a duplicate.
  await page.reload();
  await expect(feed.getByRole("listitem")).toHaveCount(1);
});
