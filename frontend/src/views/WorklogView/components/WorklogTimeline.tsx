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
 *
 * A flat list with hairline dividers rather than a timeline rule: the divider is
 * deliberately fainter than a card border so a long month reads as one block of
 * the user's record instead of a stack of chrome.
 */
export function WorklogTimeline({ groups, sources, onEdit, onArchive }: WorklogTimelineProps) {
  return (
    <div className="flex flex-col gap-6">
      {groups.map((group) => (
        <section key={group.key} aria-label={group.label} className="flex flex-col gap-1">
          <h2 className="text-muted-foreground caption">{group.label}</h2>
          <ul className="divide-border/60 border-border/60 divide-y border-t">
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
