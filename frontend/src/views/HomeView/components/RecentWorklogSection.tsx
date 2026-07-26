import { formatDayYear } from "@/lib/formatDate";

import type { HomeSection, WorklogSummary } from "../types";

interface RecentWorklogSectionProps {
  section: HomeSection<WorklogSummary>;
}

/**
 * The recent-worklog region on Home: the newest entries as title + date rows.
 * Presentational only; the Home data hook owns the fetch, ordering, and cap and
 * hands this a per-section status so a failed read blanks this region alone.
 */
export function RecentWorklogSection({ section }: RecentWorklogSectionProps) {
  return (
    <section aria-label="Recent worklog" className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold tracking-tight">Recent worklog</h2>

      {section.status === "loading" && (
        <p className="text-sm text-muted-foreground">Loading worklog…</p>
      )}

      {section.status === "error" && (
        <p role="alert" className="text-sm text-destructive">
          Could not load your recent worklog.
        </p>
      )}

      {section.status === "ready" && section.items.length === 0 && (
        <p className="text-sm text-muted-foreground">No worklog entries yet.</p>
      )}

      {section.status === "ready" && section.items.length > 0 && (
        <ul className="flex flex-col gap-2">
          {section.items.map((entry) => (
            <li
              key={entry.id}
              className="flex items-center justify-between gap-3 rounded-md border px-4 py-3"
            >
              <span className="font-medium">{entry.title}</span>
              <time dateTime={entry.entry_date} className="text-xs text-muted-foreground">
                {formatDayYear(entry.entry_date)}
              </time>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
