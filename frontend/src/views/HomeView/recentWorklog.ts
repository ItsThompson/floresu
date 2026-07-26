import type { WorklogSummary } from "./types";

/**
 * The newest worklog entries for the Home preview: newest `entry_date` first,
 * ties broken by newest id, capped at `cap`. ISO day strings compare
 * lexicographically in chronological order, so the date sort needs no parsing.
 */
export function selectRecentWorklog(entries: WorklogSummary[], cap: number): WorklogSummary[] {
  return [...entries]
    .sort((a, b) => {
      if (a.entry_date !== b.entry_date) return a.entry_date < b.entry_date ? 1 : -1;
      return b.id - a.id;
    })
    .slice(0, cap);
}
