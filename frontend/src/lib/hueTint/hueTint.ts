import type { CSSProperties } from "react";

// Fixed for every hue-tinted surface: only the fill strength varies by surface.
const INK_MIX_PERCENT = 70;

/**
 * The fill and ink for one hashed hue, both mixed from that single hue.
 *
 * The palette hues in `frontend/src/theme/tokens.css` are muted pastels, so they
 * cannot carry light ink: text on a hue-filled surface is a deeper mix of the same
 * hue rather than a separate color. Reading both shades from one place keeps a
 * fill and its ink from drifting apart, and `fillPercent` is the only part a
 * surface chooses for itself.
 */
export function hueTint(hue: string, fillPercent: number): CSSProperties {
  return {
    backgroundColor: `color-mix(in oklab, ${hue} ${fillPercent}%, var(--card))`,
    color: `color-mix(in oklab, ${hue} ${INK_MIX_PERCENT}%, var(--foreground))`,
  };
}
