import { expect, request as playwrightRequest, type APIRequestContext } from "@playwright/test";

import { INTERNAL_API_TOKEN, INTERNAL_API_URL } from "./env";
import { bodyText } from "./support";

/**
 * The internal trust boundary (:8001) is what the MCP server proxies to: a
 * validated `X-Internal-Api-Token` plus the trusted `X-User-ID` and the agent's
 * `X-Actor` label. Driving it directly is the lightweight stand-in for a full MCP
 * client, and it is exactly the boundary that carries the agent guarantees
 * (internal-denies-without-token, agent-has-no-delete-route, agent attribution).
 */
export const AGENT_LABEL = "e2e-agent";

/** An API context bound to the internal app, presenting the agent's trusted headers. */
export async function agentContext(userId: number): Promise<APIRequestContext> {
  return playwrightRequest.newContext({
    baseURL: INTERNAL_API_URL,
    extraHTTPHeaders: {
      "X-Internal-Api-Token": INTERNAL_API_TOKEN,
      "X-User-ID": String(userId),
      "X-Actor": AGENT_LABEL,
    },
  });
}

/** An internal-app context WITHOUT the token, to prove the boundary fails closed. */
export async function unauthenticatedInternalContext(): Promise<APIRequestContext> {
  return playwrightRequest.newContext({ baseURL: INTERNAL_API_URL });
}

/** Create a worklog entry as the agent, over the internal boundary. */
export async function agentCreateWorklog(
  agent: APIRequestContext,
  entry: { title: string; entryDate: string; description?: string },
): Promise<{ id: number }> {
  const response = await agent.post("/worklog", {
    data: {
      title: entry.title,
      entry_date: entry.entryDate,
      description: entry.description ?? null,
      tags: [],
      source_ids: [],
    },
  });
  expect(response.ok(), await bodyText(response)).toBeTruthy();
  return (await response.json()) as { id: number };
}

/** Update an existing worklog entry as the agent, over the internal boundary. */
export async function agentUpdateWorklog(
  agent: APIRequestContext,
  worklogId: number,
  entry: { title: string; entryDate: string; description?: string },
): Promise<void> {
  const response = await agent.put(`/worklog/${worklogId}`, {
    data: {
      title: entry.title,
      entry_date: entry.entryDate,
      description: entry.description ?? null,
      tags: [],
      source_ids: [],
    },
  });
  expect(response.ok(), await bodyText(response)).toBeTruthy();
}
