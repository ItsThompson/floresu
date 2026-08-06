import { expect, test } from "@playwright/test";

import { AGENT_LABEL, agentContext, agentCreateWorklog } from "../harness/agent";
import { createWorklog, getMe, registerAndOnboard } from "../harness/support";

/**
 * The live SSE activity feed reflects a human action. With Home open and its feed
 * stream connected, a write performed through the API pushes a single event to
 * the feed with no duplicate, and a reload (history replay) still shows exactly
 * one row.
 */
test("the activity feed reflects a human action live", async ({ page }) => {
  await registerAndOnboard(page);

  await page.goto("/home");
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

/**
 * An agent write (over the internal boundary the MCP server proxies to) streams
 * into the already-open feed live, exactly as a human write does, styled with the
 * agent actor. Home is opened first (feed stream connected, empty), then the agent
 * write is performed with no reload before the assertion, so this asserts the live
 * SSE path rather than the history replay a reload would trigger.
 */
test("an agent write streams into the open feed live", async ({ page }) => {
  await registerAndOnboard(page);
  const me = await getMe(page.request);

  await page.goto("/home");
  const feed = page.getByRole("region", { name: "Activity feed" });
  await expect(feed.getByText("No activity yet.")).toBeVisible();

  // The agent write goes over the internal boundary while the feed stream is open;
  // the fix makes the internal app publish it to the SSE channel the feed reads.
  const agent = await agentContext(me.id);
  await agentCreateWorklog(agent, { title: "Agent live entry", entryDate: "2026-05-01" });

  // It arrives over SSE with no reload, attributed to the agent (label + bot glyph).
  await expect(feed.getByRole("listitem")).toHaveCount(1);
  await expect(feed.getByText(AGENT_LABEL)).toBeVisible();
  await expect(feed.getByTestId("agent-glyph").first()).toBeVisible();

  await agent.dispose();
});
