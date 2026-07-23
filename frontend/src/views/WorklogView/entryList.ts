import { formatMonthLabel } from "./dateFormat";
import type { MonthGroup, WorklogFilterValues, WorklogSummary } from "./types";

/**
 * Keep only the entries that pass every active filter. A `null` filter is
 * inactive; the rest combine (all must pass). ISO date strings compare
 * lexicographically in chronological order, so the range check needs no parsing.
 */
export function filterEntries(entries: WorklogSummary[], filters: WorklogFilterValues): WorklogSummary[] {
  return entries.filter((entry) => {
    if (filters.sourceId !== null && !entry.source_ids.includes(filters.sourceId)) return false;
    if (filters.tag !== null && !entry.tags.includes(filters.tag)) return false;
    if (filters.dateFrom !== null && entry.entry_date < filters.dateFrom) return false;
    if (filters.dateTo !== null && entry.entry_date > filters.dateTo) return false;
    return true;
  });
}

/**
 * Group entries into months, newest month first and newest entry first within a
 * month. Same-day entries fall back to newest id first for a stable order.
 */
export function groupEntriesByMonth(entries: WorklogSummary[]): MonthGroup[] {
  const sorted = [...entries].sort((a, b) => {
    if (a.entry_date !== b.entry_date) return a.entry_date < b.entry_date ? 1 : -1;
    return b.id - a.id;
  });

  const buckets = new Map<string, WorklogSummary[]>();
  for (const entry of sorted) {
    const key = entry.entry_date.slice(0, 7);
    const bucket = buckets.get(key);
    if (bucket) bucket.push(entry);
    else buckets.set(key, [entry]);
  }

  return [...buckets].map(([key, groupedEntries]) => ({
    key,
    label: formatMonthLabel(`${key}-01`),
    entries: groupedEntries,
  }));
}
