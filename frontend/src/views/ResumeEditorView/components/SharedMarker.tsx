import { Flag } from "lucide-react";

interface SharedMarkerProps {
  usedIn: number;
}

/**
 * The shared-bullet marker: a flag plus the "used in N" count. It signals that
 * editing this bullet may prompt for scope, and encodes meaning with a glyph and
 * text (never color alone).
 */
export function SharedMarker({ usedIn }: SharedMarkerProps) {
  return (
    <span className="text-muted-foreground inline-flex items-center gap-1 text-xs" title="Shared bullet">
      <Flag aria-hidden className="size-3" /> used in {usedIn}
    </span>
  );
}
