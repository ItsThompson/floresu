import { expect, test } from "@playwright/test";

import {
  AGENT_LABEL,
  agentContext,
  agentCreateWorklog,
  unauthenticatedInternalContext,
} from "../harness/agent";
import { pkcePair, registerClient, startAuthorization } from "../harness/oauth";
import { getMe, registerAndOnboard } from "../harness/support";

/**
 * The agent boundary, end to end. A human drives the OAuth consent screen to
 * connect an agent, which then appears in Settings. An agent write (over the
 * internal boundary the MCP server proxies to) is attributed in the feed with the
 * agent's stable color and bot glyph. The internal boundary denies without the
 * token, and the agent has no delete route (web-only lifecycle).
 *
 * Coverage boundary: this drives the OAuth authorization-server consent + the
 * internal write boundary directly rather than running a full MCP client loop.
 * The MCP transport, token audience binding, and tool surface are covered by the
 * `mcp` and `contract` suites; this asserts the product-visible ends of the path.
 */
test("connect an agent via consent; attribute its write; boundaries fail closed", async ({
  page,
}) => {
  await registerAndOnboard(page);

  // The post-approval redirect targets the agent's loopback; stub it so the
  // navigation lands harmlessly (the grant is recorded at approval).
  await page.route("http://127.0.0.1:8765/**", (route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: "<html>ok</html>" }),
  );

  // Drive the OAuth consent screen.
  const clientId = await registerClient(page.request, "E2E Agent");
  const { challenge } = pkcePair();
  const authRequestId = await startAuthorization(page.request, clientId, challenge);

  await page.goto(`/authorize?auth_request_id=${authRequestId}`);
  await expect(page.getByRole("heading", { name: /Connect .*E2E Agent.* to Floresu/ })).toBeVisible();
  await expect(page.getByText(/It will read and write/)).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();

  // The connected agent appears in Settings.
  await page.goto("/settings/agents");
  await expect(page.getByText("E2E Agent")).toBeVisible();

  // An agent write over the internal boundary is attributed in the feed with the
  // agent's label and bot glyph.
  const me = await getMe(page.request);
  const agent = await agentContext(me.id);
  await agentCreateWorklog(agent, { title: "Agent authored entry", entryDate: "2026-06-01" });

  await page.goto("/");
  const feed = page.getByRole("region", { name: "Activity feed" });
  await expect(feed.getByText(AGENT_LABEL)).toBeVisible();
  await expect(feed.getByTestId("agent-glyph").first()).toBeVisible();

  // The internal boundary denies without the token.
  const anon = await unauthenticatedInternalContext();
  const denied = await anon.get("/worklog");
  expect(denied.status()).toBe(401);

  // The agent has no delete route: the web-only lifecycle is absent on the
  // internal app.
  const del = await agent.delete("/worklog/1");
  expect([404, 405]).toContain(del.status());

  await agent.dispose();
  await anon.dispose();
});
