import { useState } from "react";

import { McpUrlField } from "@/components/McpUrlField";
import { resolveMcpUrl } from "@/lib/mcpUrl";

import { ACCESS_STATEMENT } from "../constants";
import { useConnectedAgents } from "../hooks/useConnectedAgents";
import type { ConnectedClient } from "../types";
import { ConfirmDestructiveDialog } from "./ConfirmDestructiveDialog";
import { ConnectedClientRow } from "./ConnectedClientRow";

/**
 * The Connected agents section: the MCP URL to add an agent, the list of
 * connected agents with connect/last-active times and a revoke control, and the
 * single access level. Revoking is confirm-gated; on confirm the agent's grant is
 * torn down server-side and it can reconnect only through fresh consent.
 */
export function ConnectedAgentsPanel() {
  const mcpUrl = resolveMcpUrl();
  const { state, actions } = useConnectedAgents();
  const [pendingRevoke, setPendingRevoke] = useState<ConnectedClient | null>(null);

  const confirmRevoke = () => {
    if (!pendingRevoke) return;
    actions.revoke(pendingRevoke.client_id);
    setPendingRevoke(null);
  };

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold tracking-tight">Connect an agent</h2>
        <p className="text-muted-foreground text-sm">Add this MCP URL to your AI client.</p>
        <McpUrlField url={mcpUrl} />
        <p className="text-muted-foreground text-sm">Access: {ACCESS_STATEMENT}</p>
      </section>

      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold tracking-tight">Connected agents</h3>
        {state.status === "loading" && (
          <p className="text-muted-foreground text-sm">Loading connected agents…</p>
        )}
        {state.status === "error" && (
          <p role="alert" className="text-destructive text-sm">
            {state.loadError}
          </p>
        )}
        {state.status === "ready" && state.clients.length === 0 && (
          <p className="text-muted-foreground text-sm">No agents are connected yet.</p>
        )}
        {state.status === "ready" && state.clients.length > 0 && (
          <ul className="flex flex-col gap-2">
            {state.clients.map((client) => (
              <ConnectedClientRow
                key={client.client_id}
                client={client}
                isRevoking={state.revokingId === client.client_id}
                onRevoke={() => setPendingRevoke(client)}
              />
            ))}
          </ul>
        )}
        {state.revokeError && (
          <p role="alert" className="text-destructive text-sm">
            {state.revokeError}
          </p>
        )}
      </section>

      {pendingRevoke && (
        <ConfirmDestructiveDialog
          title={`Revoke ${pendingRevoke.client_name}?`}
          description="This agent loses access immediately. It can reconnect only if you approve fresh consent."
          confirmLabel="Revoke"
          onConfirm={confirmRevoke}
          onCancel={() => setPendingRevoke(null)}
        />
      )}
    </div>
  );
}
