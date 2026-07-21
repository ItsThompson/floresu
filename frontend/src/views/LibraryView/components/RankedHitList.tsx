import type { RankedHitListProps } from "../types";

const TYPE_LABELS: Record<RankedHitListProps["rows"][number]["type"], string> = {
  worklog: "Worklog",
  bullet: "Bullet",
  source: "Source",
};

/**
 * The flat RRF-ranked relevance list: every hit in ranked order, each tagged
 * with its kind. This is where a hit with no source (an unattached worklog
 * entry or bullet) still surfaces, since the grouped view lists only sources.
 */
export function RankedHitList({ rows }: RankedHitListProps) {
  return (
    <ol className="flex flex-col gap-2">
      {rows.map((row) => (
        <li
          key={row.key}
          className="border-border flex items-start gap-2 rounded-md border p-3 text-sm"
        >
          <span className="bg-muted text-muted-foreground shrink-0 rounded px-1.5 py-0.5 text-xs font-medium">
            {TYPE_LABELS[row.type]}
          </span>
          <span className="min-w-0">{row.label}</span>
        </li>
      ))}
    </ol>
  );
}
