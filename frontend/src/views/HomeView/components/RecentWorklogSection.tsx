import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { formatDayYear } from "@/lib/formatDate";
import { worklogNewEntryPath } from "@/lib/worklogPaths";

import type { HomeSection, WorklogSummary } from "../types";

interface RecentWorklogSectionProps {
  section: HomeSection<WorklogSummary>;
}

/**
 * The recent-worklog region on Home: the newest entries as title + date rows.
 * Presentational only; the Home data hook owns the fetch, ordering, and cap and
 * hands this a per-section status so a failed read blanks this region alone.
 *
 * A calm card, with one exception: its empty state is Home's single serif display
 * moment, because logging the first entry is the one thing a new account needs to
 * do. The sibling regions keep their empty states in the calm register so no more
 * than one display line can ever render here.
 */
export function RecentWorklogSection({ section }: RecentWorklogSectionProps) {
  return (
    <section
      aria-label="Recent worklog"
      className="bg-card text-card-foreground border-border flex flex-col gap-3 rounded-lg border p-6"
    >
      <h2 className="text-lg font-semibold tracking-tight">Recent worklog</h2>

      {section.status === "loading" && (
        <p className="text-muted-foreground text-sm">Loading worklog…</p>
      )}

      {section.status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          Could not load your recent worklog.
        </p>
      )}

      {section.status === "ready" && section.items.length === 0 && (
        <div className="flex flex-col items-start gap-3">
          <p className="display-m">Start with what you did today.</p>
          <p className="text-muted-foreground text-sm">No worklog entries yet.</p>
          <Button asChild>
            <Link to={worklogNewEntryPath()}>Log an entry</Link>
          </Button>
        </div>
      )}

      {section.status === "ready" && section.items.length > 0 && (
        <ul className="flex flex-col gap-2">
          {section.items.map((entry) => (
            <li key={entry.id} className="flex items-center justify-between gap-3">
              <span className="truncate font-medium">{entry.title}</span>
              <time
                dateTime={entry.entry_date}
                className="text-muted-foreground mono-meta shrink-0"
              >
                {formatDayYear(entry.entry_date)}
              </time>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
