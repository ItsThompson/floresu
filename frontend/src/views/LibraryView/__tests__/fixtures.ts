import type { Bullet, SearchResult, Source, Tag, WorklogEntry } from "../types";

export function buildSource(overrides: Partial<Source> = {}): Source {
  return {
    id: 1,
    kind: "role",
    display_label: "Acme — Senior Engineer",
    date_start: null,
    date_end: null,
    summary: null,
    sort_order: 0,
    archived_at: null,
    ...overrides,
  };
}

export function buildBullet(overrides: Partial<Bullet> = {}): Bullet {
  return {
    id: 1,
    text: "Cut checkout latency 40%",
    source_ids: [1],
    worklog_ids: [],
    used_in_count: 0,
    revision: 1,
    archived_at: null,
    ...overrides,
  };
}

export function buildWorklogEntry(overrides: Partial<WorklogEntry> = {}): WorklogEntry {
  return {
    id: 1,
    title: "Shipped payments migration",
    entry_date: "2026-07-18",
    description: null,
    tags: ["backend"],
    source_ids: [1],
    archived_at: null,
    ...overrides,
  };
}

export function buildTag(overrides: Partial<Tag> = {}): Tag {
  return { id: 1, label: "backend", ...overrides };
}

export function buildSearchResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    ranked: [],
    graph: { sources: [], worklog: [], bullets: [] },
    notices: [],
    ...overrides,
  };
}
