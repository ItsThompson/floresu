import { useState } from "react";

import { McpUrlField } from "@/components/McpUrlField";
import { resolveMcpUrl } from "@/lib/mcpUrl";

import { ACCESS_STATEMENT } from "../constants";
import { useConnectedAgents } from "../hooks/useConnectedAgents";
import type { ConnectedClient } from "../types";
import { ConfirmDestructiveDialog } from "./ConfirmDestructiveDialog";
import { ConnectedClientRow } from "./ConnectedClientRow";
import { SettingsPanel } from "./SettingsPanel";

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
    <div className="flex flex-col gap-4">
      <SettingsPanel title="Connect an agent" description="Add this MCP URL to your AI client.">
        <McpUrlField url={mcpUrl} />
        <p className="caption text-muted-foreground">Access: {ACCESS_STATEMENT}</p>
      </SettingsPanel>

      <SettingsPanel title="Connected agents">
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
          <ul className="divide-border/60 flex flex-col divide-y">
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
      </SettingsPanel>

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
