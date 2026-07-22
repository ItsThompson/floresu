import { colorForName } from "@/lib/colorForName";

interface TagPillProps {
  label: string;
}

/**
 * A worklog tag pill. The color comes from the shared `colorForName` domain truth
 * (never re-derived here); the label text always shows, so meaning never rests on
 * color alone.
 */
export function TagPill({ label }: TagPillProps) {
  return (
    <span className="border-border inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs">
      <span
        aria-hidden
        className="size-2 rounded-full"
        style={{ backgroundColor: colorForName(label) }}
      />
      {label}
    </span>
  );
}
