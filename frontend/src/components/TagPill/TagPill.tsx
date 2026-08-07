import { colorForName } from "@/lib/colorForName";
import { hueTint } from "@/lib/hueTint";

interface TagPillProps {
  label: string;
  /** Trailing ✕ control, rendered where a tag can be detached from its entry. */
  onRemove?: () => void;
}

// Lighter than the identity avatars: a pill sits inline in running text, so its
// fill has to read as a tint rather than as a block of color.
const FILL_PERCENT = 18;

/**
 * A tag chip. Its hue is the shared `colorForName` hash of the label, so one tag
 * is one color everywhere it appears, and the fill needs no border because the
 * tint is the pill's edge. The "#label" text always renders, so a tag never
 * carries meaning by color alone.
 */
export function TagPill({ label, onRemove }: TagPillProps) {
  return (
    <span
      className="mono-tag inline-flex items-center gap-1 rounded-full px-2 py-1 whitespace-nowrap"
      style={hueTint(colorForName(label), FILL_PERCENT)}
    >
      {`#${label}`}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove tag ${label}`}
          className="rounded-full leading-none hover:opacity-70"
        >
          ×
        </button>
      )}
    </span>
  );
}
