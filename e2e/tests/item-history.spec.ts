import { expect, test } from "@playwright/test";

import { AGENT_LABEL, agentContext, agentUpdateWorklog } from "../harness/agent";
import { createWorklog, getMe, registerAndOnboard } from "../harness/support";

/**
 * The per-item audit history is reachable from a worklog entry, and it reflects
 * both human and agent writes. A human creates an entry, then an agent updates it
 * over the internal boundary the MCP server proxies to. Opening the entry's
 * History shows both rows, newest-first, attributing the human and the named agent
 * distinctly (by avatar color and the bot-glyph shape, not color alone).
 */
test("open an item's history showing both a human and an agent write", async ({ page }) => {
  await registerAndOnboard(page);

  // A human create, then an agent update on the same entry.
  const entry = await createWorklog(page.request, {
    title: "Shipped the beta",
    entryDate: "2026-04-01",
  });
  const me = await getMe(page.request);
  const agent = await agentContext(me.id);
  await agentUpdateWorklog(agent, entry.id, {
    title: "Shipped the beta (revised)",
    entryDate: "2026-04-01",
  });

  // Open the entry's history from its overflow menu.
  await page.goto("/worklog");
  await page.getByRole("button", { name: "Actions for Shipped the beta (revised)" }).click();
  await page.getByRole("button", { name: "History" }).click();

  const dialog = page.getByRole("dialog", { name: "History: Shipped the beta (revised)" });
  await expect(dialog).toBeVisible();

  // Both writes appear, distinctly attributed: the human ("You") and the agent
  // (its label plus the bot glyph that marks an agent by shape).
  await expect(dialog.getByText("You", { exact: true })).toBeVisible();
  await expect(dialog.getByText(/created/)).toBeVisible();
  await expect(dialog.getByText(AGENT_LABEL)).toBeVisible();
  await expect(dialog.getByText(/updated/)).toBeVisible();
  await expect(dialog.getByTestId("agent-glyph")).toBeVisible();

  await agent.dispose();
});
