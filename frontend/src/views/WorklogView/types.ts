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
/** The search request body: the free-text query plus the mapped filters. */
export type SearchQuery = components["schemas"]["SearchQuery"];

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

/** A bullet framed by an entry, shown in the row's overflow menu. */
export interface DerivedBullet {
  id: number;
  text: string;
}

/**
 * The submitted-search lifecycle. Mirrors LibraryView's `SearchState`: the
 * `results` arm carries the raw response, which the shared result view derives
 * its rows and source groups from, and covers the zero-match case too. The
 * `searching` arm carries no payload, so a re-search shows no stale prior hits.
 */
export type WorklogSearchState =
  | { status: "idle" }
  | { status: "searching" }
  | { status: "results"; result: SearchResult }
  | { status: "error"; message: string };

export interface WorklogSearchActions {
  setQuery: (query: string) => void;
  submit: () => Promise<void>;
  clear: () => void;
}

/**
 * What the WorklogSearch field renders from: the controlled `query` beside the
 * search lifecycle. `query` is a separate concern from the lifecycle, so it sits
 * next to the union rather than inside it.
 */
export interface WorklogSearchViewState {
  query: string;
  search: WorklogSearchState;
}
