import { formatDayLabel } from "@/lib/dateFormat";
import { SOURCE_KIND_LABELS } from "@/lib/sourceKindLabels";

import type { SearchSourceGroup } from "./sourceGroups";

interface SearchSourceGroupCardProps {
  group: SearchSourceGroup;
}

/**
 * One source in the grouped-by-source results: the source heading (with a
 * "matched directly" note when the source's own text hit the query) followed by
 * its matched worklog entries and bullets, each in per-source relevance order.
 */
export function SearchSourceGroupCard({ group }: SearchSourceGroupCardProps) {
  return (
    <section className="bg-card border-border flex flex-col gap-2 rounded-md border p-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold tracking-tight">
        {group.label}
        <span className="mono-tag text-muted-foreground">{SOURCE_KIND_LABELS[group.kind]}</span>
        {group.matchScore !== null && (
          <span className="text-primary text-xs font-medium">matched directly</span>
        )}
      </h3>

      {group.worklog.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {group.worklog.map((entry) => (
            <li key={`worklog-${entry.id}`} className="flex items-center gap-2">
              <span className="mono-tag text-muted-foreground shrink-0">Worklog</span>
              <span className="min-w-0">
                {entry.title}
                <time className="mono-meta text-muted-foreground ml-2" dateTime={entry.date}>
                  {formatDayLabel(entry.date)}
                </time>
              </span>
            </li>
          ))}
        </ul>
      )}

      {group.bullets.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {group.bullets.map((bullet) => (
            <li key={`bullet-${bullet.id}`} className="flex items-start gap-2">
              <span className="mono-tag text-muted-foreground shrink-0 pt-1">Bullet</span>
              <span className="min-w-0">{bullet.text}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
