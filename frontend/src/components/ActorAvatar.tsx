import type { components } from "@/api";

import { AgentAvatar } from "./AgentAvatar";

interface ActorAvatarProps {
  actorType: components["schemas"]["AuditEntry"]["actor_type"];
  actorLabel: string | null;
}

const HUMAN_LABEL = "You";

/**
 * The actor's identity chip on every audit-read surface: the activity feed and
 * per-item history. Human and agent are distinguished by BOTH color and shape (an
 * agent carries a bot glyph badge, the human does not), never by color alone, per
 * the accessibility rule.
 *
 * An agent renders as `AgentAvatar`, which is what keeps one agent looking the
 * same here as it does in Settings. The human is always the accent coral token
 * pair (see `docs/design-language.md`), never a hashed hue: "you" reads the same
 * everywhere. A hairline ring keeps the disc readable on a surface that shares its
 * own accent fill, such as the highlighted newest row in the activity feed.
 */
export function ActorAvatar({ actorType, actorLabel }: ActorAvatarProps) {
  if (actorType === "agent") return <AgentAvatar name={actorLabel ?? "Agent"} />;

  return (
    <span className="relative inline-flex shrink-0" aria-label={HUMAN_LABEL} role="img">
      <span className="bg-accent text-accent-foreground ring-border flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold ring-1">
        {HUMAN_LABEL.charAt(0)}
      </span>
    </span>
  );
}
