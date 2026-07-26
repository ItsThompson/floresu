import { ActorAvatar } from "@/components/ActorAvatar";
import { actionLabel } from "@/lib/actionLabel";

import type { AuditEntry } from "./hooks/useItemHistory";

interface ItemHistoryRowProps {
  entry: AuditEntry;
}

/**
 * One audit-trail row: the actor avatar (color + bot glyph), who did what, an
 * optional summary, and when. Human-vs-agent is distinguished by the avatar's
 * color and shape, consistent with the live activity feed.
 */
export function ItemHistoryRow({ entry }: ItemHistoryRowProps) {
  const actorName = entry.actor_type === "agent" ? (entry.actor_label ?? "Agent") : "You";

  return (
    <li className="flex items-start gap-3 rounded-md border border-border p-3">
      <ActorAvatar actorType={entry.actor_type} actorLabel={entry.actor_label} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <p className="text-sm">
          <span className="font-medium">{actorName}</span> {actionLabel(entry.action)}
        </p>
        {entry.summary && <p className="truncate text-sm text-muted-foreground">{entry.summary}</p>}
        <time dateTime={entry.created_at} className="text-xs text-muted-foreground">
          {new Date(entry.created_at).toLocaleString()}
        </time>
      </div>
    </li>
  );
}
