import { colorForName } from "@/lib/colorForName";
import { cn } from "@/lib/utils";

interface TagPillProps {
  label: string;
  /** Optional remove control, shown as a trailing ✕ (used in the entry form). */
  onRemove?: () => void;
}

/**
 * A tag chip whose color is the shared `colorForName` hash of its label, so the
 * same tag is the same color everywhere it appears. Color is decorative: the
 * "#label" text carries the meaning, so the pill is legible without relying on
 * color alone.
 */
export function TagPill({ label, onRemove }: TagPillProps) {
  const color = colorForName(label);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
      )}
      style={{ borderColor: color, color }}
    >
      {`#${label}`}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove tag ${label}`}
          className="ml-0.5 rounded-full leading-none hover:opacity-70"
        >
          ×
        </button>
      )}
    </span>
  );
}
