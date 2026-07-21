import type {
  MonthGroup,
  ResolvedHit,
  SearchResult,
  SourceSummary,
  WorklogFilters,
  WorklogSummary,
} from "./types";

// UTC formatters: entry dates are calendar dates (`yyyy-mm-dd`) with no zone, so
// formatting in UTC avoids a local-timezone off-by-one on the day and month.
const MONTH_LABEL = new Intl.DateTimeFormat("en-US", {
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});
const DAY_LABEL = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "2-digit",
  timeZone: "UTC",
});

/** Format an entry date as its full month, e.g. "July 2026". */
export function formatMonthLabel(isoDate: string): string {
  return MONTH_LABEL.format(new Date(isoDate));
}

/** Format an entry date as a short day, e.g. "Jul 18". */
export function formatDayLabel(isoDate: string): string {
  return DAY_LABEL.format(new Date(isoDate));
}

/**
 * Keep only the entries that pass every active filter. A `null` filter is
 * inactive; the rest combine (all must pass). ISO date strings compare
 * lexicographically in chronological order, so the range check needs no parsing.
 */
export function filterEntries(entries: WorklogSummary[], filters: WorklogFilters): WorklogSummary[] {
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

/** The display label for a source id, or a stable fallback if it is unknown. */
export function sourceLabel(sources: SourceSummary[], sourceId: number): string {
  return sources.find((source) => source.id === sourceId)?.display_label ?? `Source ${sourceId}`;
}

/**
 * Join each flat ranked hit to its graph node so it carries a human label. A hit
 * with no matching node is dropped rather than rendered label-less. Order is
 * preserved, so the fused RRF ranking is what the UI shows.
 */
export function resolveRankedHits(result: SearchResult): ResolvedHit[] {
  const worklog = new Map(result.graph.worklog.map((node) => [node.id, node]));
  const bullets = new Map(result.graph.bullets.map((node) => [node.id, node]));
  const sources = new Map(result.graph.sources.map((node) => [node.id, node]));

  return result.ranked.flatMap<ResolvedHit>((hit) => {
    if (hit.type === "worklog") {
      const node = worklog.get(hit.id);
      if (!node) return [];
      return [{ ...hit, label: node.title, detail: formatDayLabel(node.date) }];
    }
    if (hit.type === "bullet") {
      const node = bullets.get(hit.id);
      if (!node) return [];
      return [{ ...hit, label: node.text, detail: null }];
    }
    const node = sources.get(hit.id);
    if (!node) return [];
    return [{ ...hit, label: node.label, detail: node.kind }];
  });
}
