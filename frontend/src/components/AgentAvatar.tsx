import { Bot } from "lucide-react";

import { colorForName } from "@/lib/colorForName";

interface AgentAvatarProps {
  name: string;
}

/**
 * An agent's identity chip: a circular avatar colored by `colorForName` with the
 * name's initial and a bot glyph badge. The hue is stable per agent name, so an
 * agent looks the same everywhere it appears (the activity feed, audit views, and
 * Settings), and the glyph marks it as an agent by shape, not by color alone.
 */
export function AgentAvatar({ name }: AgentAvatarProps) {
  const initial = name.charAt(0).toUpperCase();

  return (
    <span className="relative inline-flex shrink-0" aria-label={name} role="img">
      <span
        className="flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold text-white"
        style={{ backgroundColor: colorForName(name) }}
      >
        {initial}
      </span>
      <span
        className="bg-background text-foreground ring-border absolute -right-1 -bottom-1 flex h-4 w-4 items-center justify-center rounded-full ring-1"
        data-testid="agent-glyph"
      >
        <Bot className="h-3 w-3" aria-hidden="true" />
      </span>
    </span>
  );
}
