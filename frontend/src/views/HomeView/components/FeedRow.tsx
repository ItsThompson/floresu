import { Link } from "react-router";

import { ActorAvatar } from "@/components/ActorAvatar";
import { actionLabel } from "@/lib/actionLabel";
import { cn } from "@/lib/utils";

import { entityHref, entityLabel } from "../constants";
import type { FeedEvent } from "../types";

interface FeedRowProps {
  event: FeedEvent;
  /** Play the entrance animation. False when the user prefers reduced motion. */
  animate: boolean;
  /** The most recent event, which carries the accent tint. */
  isNewest: boolean;
}

/**
 * The ink a row's link and timestamp carry, by surface. On the accent tint the
 * calm shades miss the 4.5:1 floor (the coral link measures 4.00:1 there and the
 * muted timestamp 4.49:1), so the tinted row swaps in the deeper coral the accent
 * token pair provides and full-strength ink for the time.
 */
const ROW_INK = {
  tinted: { link: "text-accent-foreground", timestamp: "text-foreground" },
  calm: { link: "text-primary", timestamp: "text-muted-foreground" },
} as const;

/**
 * One activity-feed row: the actor avatar, who did what, the affected object as a
 * link, and when. The avatar carries the row's only color, except on the newest
 * row, which is tinted until a newer event displaces it. The entrance animation is
 * applied only when motion is allowed.
 */
export function FeedRow({ event, animate, isNewest }: FeedRowProps) {
  const actorName = event.actor_type === "agent" ? (event.actor_label ?? "Agent") : "You";
  const ink = isNewest ? ROW_INK.tinted : ROW_INK.calm;

  return (
    <li
      className={cn(
        "flex items-center gap-3 p-3",
        isNewest && "bg-accent",
        animate && "animate-in fade-in slide-in-from-top-1",
      )}
    >
      <ActorAvatar actorType={event.actor_type} actorLabel={event.actor_label} />
      <div className="flex min-w-0 flex-1 flex-col">
        <p className="truncate text-sm">
          <span className="font-medium">{actorName}</span> {actionLabel(event.action)}{" "}
          <Link to={entityHref(event)} className={cn("font-medium hover:underline", ink.link)}>
            {entityLabel(event)}
          </Link>
        </p>
        <time dateTime={event.created_at} className={cn("mono-meta", ink.timestamp)}>
          {new Date(event.created_at).toLocaleString()}
        </time>
      </div>
    </li>
  );
}
