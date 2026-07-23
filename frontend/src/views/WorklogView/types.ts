import type { components } from "@/api";

/** The timeline row: an entry with its tags and attached source ids. */
export type WorklogSummary = components["schemas"]["WorklogSummary"];
/** A single entry with its provenance edges (adds `bullet_ids`). */
export type WorklogRecord = components["schemas"]["WorklogRecord"];
/** The create/update body: required title + date; optional description, tags, sources. */
export type WorklogWrite = components["schemas"]["WorklogWrite"];
/** A profile source (role/project/cert/education) used for links and the filter. */
export type SourceSummary = components["schemas"]["SourceSummary"];
/** A reuse-list tag; color is derived from the label, never carried. */
export type TagRead = components["schemas"]["TagRead"];
/** A canonical bullet with its provenance edges (used for derived-bullet lists). */
export type BulletpointRecord = components["schemas"]["BulletpointRecord"];
/** The hybrid-search response: flat ranked list, scored graph, and soft notices. */
export type SearchResult = components["schemas"]["SearchResult"];
/** One flat ranked hit: kind + id + fused score. */
export type RankedHit = components["schemas"]["RankedHit"];

/** The timeline's load lifecycle. `ready` covers the empty timeline too. */
export type WorklogStatus = "loading" | "ready" | "error";

/** The three filters that narrow the timeline; all applied together. */
export interface WorklogFilterValues {
  sourceId: number | null;
  tag: string | null;
  /** Inclusive ISO date bounds (`yyyy-mm-dd`); `null` means unbounded. */
  dateFrom: string | null;
  dateTo: string | null;
}

/** One month's worth of entries, newest month first, newest entry first within. */
export interface MonthGroup {
  /** `yyyy-mm`, the stable group key. */
  key: string;
  /** Human label, e.g. "July 2026". */
  label: string;
  entries: WorklogSummary[];
}

/** The controlled values of the create/edit form. */
export interface EntryFormValues {
  title: string;
  /** ISO date `yyyy-mm-dd`. */
  entryDate: string;
  description: string;
  tags: string[];
  sourceIds: number[];
}

/** Which form is open: none, a fresh create, or an edit of a known entry. */
export type FormMode =
  | { kind: "closed" }
  | { kind: "create" }
  | { kind: "edit"; entryId: number };

/** A ranked hit resolved against the graph so it carries a human label. */
export interface ResolvedHit {
  type: RankedHit["type"];
  id: number;
  score: number;
  /** The worklog title, bullet text, or source label. */
  label: string;
  /** Secondary line: a worklog date or a source kind; `null` for bullets. */
  detail: string | null;
}

/** A bullet framed by an entry, shown in the row's overflow menu. */
export interface DerivedBullet {
  id: number;
  text: string;
}
