import { Bot } from "lucide-react";

import { colorForName } from "@/lib/colorForName";
import { hueTint } from "@/lib/hueTint";

interface AgentAvatarProps {
  name: string;
}

// Heavier than a tag pill's: the swatch is a solid 32px disc, not inline text.
const FILL_PERCENT = 20;

/**
 * An agent's identity chip: a circular avatar with the name's initial and a bot
 * glyph badge. The hue is stable per agent name, so an agent looks the same
 * everywhere it appears (the activity feed, audit views, and Settings), and the
 * glyph marks it as an agent by shape, not by color alone.
 */
export function AgentAvatar({ name }: AgentAvatarProps) {
  const initial = name.charAt(0).toUpperCase();

  return (
    <span className="relative inline-flex shrink-0" aria-label={name} role="img">
      <span
        className="flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold"
        style={hueTint(colorForName(name), FILL_PERCENT)}
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
