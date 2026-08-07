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
 *
 * A provenance surface, so the row itself stays calm and lets the avatar carry
 * the only color.
 */
export function ItemHistoryRow({ entry }: ItemHistoryRowProps) {
  const actorName = entry.actor_type === "agent" ? (entry.actor_label ?? "Agent") : "You";

  return (
    <li className="flex items-start gap-3 py-3">
      <ActorAvatar actorType={entry.actor_type} actorLabel={entry.actor_label} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <p className="text-muted-foreground text-sm">
          <span className="text-foreground font-medium">{actorName}</span>{" "}
          {actionLabel(entry.action)}
        </p>
        {entry.summary && <p className="text-muted-foreground truncate text-sm">{entry.summary}</p>}
        <time dateTime={entry.created_at} className="text-muted-foreground mono-meta">
          {new Date(entry.created_at).toLocaleString()}
        </time>
      </div>
    </li>
  );
}
