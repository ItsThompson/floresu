import type { MonthGroup, SourceSummary } from "../types";
import { WorklogRow } from "./WorklogRow";

interface WorklogTimelineProps {
  groups: MonthGroup[];
  sources: SourceSummary[];
  onEdit: (entryId: number) => void;
  onArchive: (entryId: number) => void;
}

/**
 * The month-grouped timeline: each group is a month heading (newest first) over
 * its entries. Rows own their own layout; this component owns only the grouping
 * structure.
 */
export function WorklogTimeline({ groups, sources, onEdit, onArchive }: WorklogTimelineProps) {
  return (
    <div className="flex flex-col gap-6">
      {groups.map((group) => (
        <section key={group.key} aria-label={group.label} className="flex flex-col gap-1">
          <h2 className="text-muted-foreground text-sm font-semibold tracking-wide uppercase">
            {group.label}
          </h2>
          <ul className="divide-border divide-y border-t">
            {group.entries.map((entry) => (
              <WorklogRow
                key={entry.id}
                entry={entry}
                sources={sources}
                onEdit={onEdit}
                onArchive={onArchive}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
