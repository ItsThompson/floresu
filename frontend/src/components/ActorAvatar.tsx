import { Bot } from "lucide-react";

import type { components } from "@/api";
import { colorForName } from "@/lib/colorForName";

// The human actor is always the design language's coral, never the hashed
// palette: "you" reads the same everywhere. Agents take a hashed color from
// colorForName so each named agent is stable and mutually distinguishable.
const HUMAN_CORAL = "hsl(6 78% 63%)";

interface ActorAvatarProps {
  actorType: components["schemas"]["AuditEntry"]["actor_type"];
  actorLabel: string | null;
}

/**
 * The actor's identity chip: a colored circular avatar with an initial. Human and
 * agent are distinguished by BOTH color and shape (agents carry a bot glyph badge,
 * the human does not), never color alone, per the accessibility rule. Shared by
 * every audit-read surface: the activity feed and per-item history.
 */
export function ActorAvatar({ actorType, actorLabel }: ActorAvatarProps) {
  const isAgent = actorType === "agent";
  const name = isAgent ? (actorLabel ?? "Agent") : "You";
  const color = isAgent ? colorForName(actorLabel ?? "agent") : HUMAN_CORAL;
  const initial = name.charAt(0).toUpperCase();

  return (
    <span className="relative inline-flex shrink-0" aria-label={name} role="img">
      <span
        className="flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold text-white"
        style={{ backgroundColor: color }}
      >
        {initial}
      </span>
      {isAgent && (
        <span
          className="absolute -bottom-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-background text-foreground ring-1 ring-border"
          data-testid="agent-glyph"
        >
          <Bot className="h-3 w-3" aria-hidden="true" />
        </span>
      )}
    </span>
  );
}
