import type { WorklogMonth } from "../hooks/useContextualWorklog";
import { WorklogEntryRow } from "./WorklogEntryRow";

interface WorklogMonthGroupProps {
  month: WorklogMonth;
}

/** A collapsible-free month bucket header with its entry count and rows. */
export function WorklogMonthGroup({ month }: WorklogMonthGroupProps) {
  return (
    <section aria-label={month.label} className="flex flex-col">
      <header className="text-muted-foreground flex items-baseline justify-between text-xs font-medium uppercase tracking-wide">
        <span>{month.label}</span>
        <span>
          {month.entries.length} {month.entries.length === 1 ? "entry" : "entries"}
        </span>
      </header>
      <ul className="divide-border flex flex-col divide-y">
        {month.entries.map((entry) => (
          <WorklogEntryRow key={entry.id} entry={entry} />
        ))}
      </ul>
    </section>
  );
}
