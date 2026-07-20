import { Link } from "react-router";

import { cn } from "@/lib/utils";

import { actionLabel, entityHref, entityLabel } from "../constants";
import type { FeedEvent } from "../types";
import { ActorAvatar } from "./ActorAvatar";

interface FeedRowProps {
  event: FeedEvent;
  /** Play the entrance animation. False when the user prefers reduced motion. */
  animate: boolean;
}

/**
 * One activity-feed row: the actor avatar, who did what, the affected object as a
 * link, and when. The entrance animation is applied only when motion is allowed.
 */
export function FeedRow({ event, animate }: FeedRowProps) {
  const actorName = event.actor_type === "agent" ? (event.actor_label ?? "Agent") : "You";

  return (
    <li
      className={cn(
        "flex items-center gap-3 rounded-md border border-border p-3",
        animate && "animate-in fade-in slide-in-from-top-1",
      )}
    >
      <ActorAvatar actorType={event.actor_type} actorLabel={event.actor_label} />
      <div className="flex min-w-0 flex-1 flex-col">
        <p className="truncate text-sm">
          <span className="font-medium">{actorName}</span> {actionLabel(event.action)}{" "}
          <Link to={entityHref(event)} className="font-medium text-primary hover:underline">
            {entityLabel(event)}
          </Link>
        </p>
        <time dateTime={event.created_at} className="text-xs text-muted-foreground">
          {new Date(event.created_at).toLocaleString()}
        </time>
      </div>
    </li>
  );
}
