import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { mockAuthUser } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/renderWithProviders";

import { formatDate } from "../constants";
import type { ConnectedClient } from "../types";

/**
 * Sociable tests for the Connected agents section: they drive the real route
 * tree, session guard, and agents state machine against the MSW-backed API. Only
 * the network is mocked.
 */

const CONNECTED_AT = "2026-07-01T09:00:00Z";
const LAST_ACTIVE_AT = "2026-07-08T10:32:00Z";

function buildClient(overrides?: Partial<ConnectedClient>): ConnectedClient {
  return {
    client_id: "client-1",
    client_name: "Claude",
    scopes: ["floresu:full"],
    connected_at: CONNECTED_AT,
    last_active_at: LAST_ACTIVE_AT,
    ...overrides,
  };
}

/** Resume-on-mount authenticates an onboarded user so the app shell renders. */
function authenticateOnResume() {
  server.use(http.post("*/auth/refresh", () => HttpResponse.json(mockAuthUser)));
}

function mockClients(clients: ConnectedClient[]) {
  server.use(http.get("*/me/clients", () => HttpResponse.json(clients)));
}

describe("ConnectedAgentsPanel", () => {
  it("shows the MCP URL with a copy control and the single access level", async () => {
    authenticateOnResume();
    mockClients([]);

    renderApp(["/settings/agents"]);

    expect(await screen.findByLabelText("MCP URL")).toHaveValue("https://mcp.floresu.com/mcp");
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
    expect(screen.getByText(/full read-write/i)).toBeInTheDocument();
  });

  it("lists connected agents with their connected and last-active times", async () => {
    authenticateOnResume();
    mockClients([buildClient(), buildClient({ client_id: "client-2", client_name: "Cursor" })]);

    renderApp(["/settings/agents"]);

    const claudeRow = (await screen.findByText("Claude")).closest("li");
    expect(claudeRow).not.toBeNull();
    expect(claudeRow).toHaveTextContent(formatDate(CONNECTED_AT));
    expect(claudeRow).toHaveTextContent(/last active/i);
    expect(screen.getByText("Cursor")).toBeInTheDocument();
  });

  it("revokes an agent after confirmation and removes it from the list", async () => {
    authenticateOnResume();
    mockClients([buildClient()]);
    let revokedId: string | null = null;
    server.use(
      http.delete("*/me/clients/:clientId", ({ params }) => {
        revokedId = params.clientId as string;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderApp(["/settings/agents"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /Revoke/ }));
    // Confirm-gated: the agent is still listed until the dialog is confirmed.
    const dialog = screen.getByRole("alertdialog");
    expect(screen.getByText("Claude")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /Revoke/ }));

    await waitFor(() => expect(screen.queryByText("Claude")).not.toBeInTheDocument());
    expect(revokedId).toBe("client-1");
  });

  it("keeps the agent when the revoke confirmation is cancelled", async () => {
    authenticateOnResume();
    mockClients([buildClient()]);
    let deleteCalled = false;
    server.use(
      http.delete("*/me/clients/:clientId", () => {
        deleteCalled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderApp(["/settings/agents"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /Revoke/ }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getByText("Claude")).toBeInTheDocument();
    expect(deleteCalled).toBe(false);
  });

  it("surfaces a load error without crashing", async () => {
    authenticateOnResume();
    server.use(http.get("*/me/clients", () => HttpResponse.error()));

    renderApp(["/settings/agents"]);

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn.t load your connected agents/i);
  });

  it("keeps the agent listed and surfaces an error when the revoke DELETE fails", async () => {
    authenticateOnResume();
    mockClients([buildClient()]);
    server.use(
      http.delete("*/me/clients/:clientId", () =>
        HttpResponse.json({ detail: "Revoke failed." }, { status: 500 }),
      ),
    );

    renderApp(["/settings/agents"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /Revoke/ }));
    const dialog = screen.getByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: /Revoke/ }));

    // The failed revoke sets revokeError (shown) without discarding the list.
    expect(await screen.findByText(/couldn.t revoke that agent/i)).toBeInTheDocument();
    expect(screen.getByText("Claude")).toBeInTheDocument();
  });
});
