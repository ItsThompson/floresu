import { X } from "lucide-react";

import { AgentAvatar } from "@/components/AgentAvatar";
import { Button } from "@/components/ui/button";

import { formatDate, formatDateTime } from "../constants";
import type { ConnectedClient } from "../types";

interface ConnectedClientRowProps {
  client: ConnectedClient;
  isRevoking: boolean;
  onRevoke: () => void;
}

/**
 * One connected agent: its identity chip and name, when it connected and last
 * acted, and a revoke control. Revoke is destructive, so it carries an `x` icon
 * and a label (not color alone); the confirmation gate is the panel's.
 */
export function ConnectedClientRow({ client, isRevoking, onRevoke }: ConnectedClientRowProps) {
  return (
    <li className="border-border flex items-center gap-3 rounded-md border p-3">
      <AgentAvatar name={client.client_name} />
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate font-medium">{client.client_name}</span>
        <span className="text-muted-foreground text-xs">
          Connected {formatDate(client.connected_at)} · last active{" "}
          {formatDateTime(client.last_active_at)}
        </span>
      </div>
      <Button variant="destructive" size="sm" onClick={onRevoke} disabled={isRevoking}>
        <X aria-hidden />
        {isRevoking ? "Revoking…" : "Revoke"}
      </Button>
    </li>
  );
}
