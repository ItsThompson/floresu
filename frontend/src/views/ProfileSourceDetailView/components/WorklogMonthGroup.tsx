import type { WorklogMonth } from "../hooks/useContextualWorklog";
import { WorklogEntryRow } from "./WorklogEntryRow";

interface WorklogMonthGroupProps {
  month: WorklogMonth;
}

/** A collapsible-free month bucket header with its entry count and rows. */
export function WorklogMonthGroup({ month }: WorklogMonthGroupProps) {
  return (
    <section aria-label={month.label} className="flex flex-col">
      <header className="text-muted-foreground flex items-baseline justify-between gap-2">
        <span className="caption">{month.label}</span>
        <span className="mono-meta">
          {month.entries.length} {month.entries.length === 1 ? "entry" : "entries"}
        </span>
      </header>
      <ul className="divide-border/60 flex flex-col divide-y">
        {month.entries.map((entry) => (
          <WorklogEntryRow key={entry.id} entry={entry} />
        ))}
      </ul>
    </section>
  );
}
