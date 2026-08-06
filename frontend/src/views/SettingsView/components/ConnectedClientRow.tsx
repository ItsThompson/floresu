import { X } from "lucide-react";

import { AgentAvatar } from "@/components/AgentAvatar";
import { Button } from "@/components/ui/button";

import { DESTRUCTIVE_ROW_ACTION_CLASS, formatDate, formatDateTime } from "../constants";
import type { ConnectedClient } from "../types";

interface ConnectedClientRowProps {
  client: ConnectedClient;
  isRevoking: boolean;
  onRevoke: () => void;
}

/**
 * One connected agent: its identity chip and name, a connected badge, when it
 * connected and last acted, and a revoke control.
 *
 * This is the provenance record for agent access, so the two timestamps are the
 * point of the row and run in tabular mono. The badge pairs its olive tint with
 * the word "Connected" and revoke pairs its crimson with an `x` glyph and a label,
 * so neither the state nor the consequence is carried by color alone. The
 * confirmation gate is the panel's.
 */
export function ConnectedClientRow({ client, isRevoking, onRevoke }: ConnectedClientRowProps) {
  return (
    <li className="flex items-center gap-3 py-3">
      <AgentAvatar name={client.client_name} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex items-center gap-2">
          <span className="text-foreground truncate text-sm font-medium">{client.client_name}</span>
          <span className="bg-success-tint text-foreground caption inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5">
            <span aria-hidden className="bg-success size-1.5 rounded-full" />
            Connected
          </span>
        </div>
        <span className="mono-meta text-muted-foreground truncate">
          Since {formatDate(client.connected_at)} · last active{" "}
          {formatDateTime(client.last_active_at)}
        </span>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={onRevoke}
        disabled={isRevoking}
        className={DESTRUCTIVE_ROW_ACTION_CLASS}
      >
        <X aria-hidden />
        {isRevoking ? "Revoking…" : "Revoke"}
      </Button>
    </li>
  );
}
