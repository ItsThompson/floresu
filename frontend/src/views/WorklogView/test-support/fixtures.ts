import type {
  BulletpointRecord,
  SearchResult,
  SourceSummary,
  TagRead,
  WorklogRecord,
  WorklogSummary,
} from "../types";

/** Build a timeline row. Defaults to a tagged, single-source July entry. */
export function buildEntry(overrides?: Partial<WorklogSummary>): WorklogSummary {
  return {
    id: 1,
    title: "Shipped payments migration",
    entry_date: "2026-07-18",
    description: "Cut over the payments service with zero downtime.",
    tags: ["backend", "payments"],
    source_ids: [10],
    archived_at: null,
    ...overrides,
  };
}

/** Build the single-entry record (adds provenance `bullet_ids`). */
export function buildEntryRecord(overrides?: Partial<WorklogRecord>): WorklogRecord {
  return {
    id: 1,
    title: "Shipped payments migration",
    entry_date: "2026-07-18",
    description: "Cut over the payments service with zero downtime.",
    tags: ["backend", "payments"],
    source_ids: [10],
    archived_at: null,
    bullet_ids: [],
    ...overrides,
  };
}

/** Build a profile source (the filter options and the row's source links). */
export function buildSource(overrides?: Partial<SourceSummary>): SourceSummary {
  return {
    id: 10,
    kind: "role",
    display_label: "Acme — Senior Engineer",
    date_start: "2024-01-01",
    date_end: null,
    summary: null,
    sort_order: 0,
    archived_at: null,
    ...overrides,
  };
}

/** Build a reuse-list tag. */
export function buildTag(overrides?: Partial<TagRead>): TagRead {
  return { id: 1, label: "backend", ...overrides };
}

/** Build a canonical bullet with its provenance edges. */
export function buildBullet(overrides?: Partial<BulletpointRecord>): BulletpointRecord {
  return {
    id: 100,
    text: "Cut checkout latency 40% by batching writes",
    source_ids: [10],
    worklog_ids: [1],
    used_in_count: 1,
    revision: 1,
    archived_at: null,
    ...overrides,
  };
}

/** Build a search response. Defaults to an empty result; override per test. */
export function buildSearchResult(overrides?: Partial<SearchResult>): SearchResult {
  return {
    ranked: [],
    graph: { sources: [], worklog: [], bullets: [] },
    notices: [],
    ...overrides,
  };
}
