import type { components } from "@/api";
import type { WriteState } from "@/lib/asyncState";
import type { SearchFilterValues } from "@/lib/searchFilters";

/** A canonical library bullet with its provenance edges and usage count. */
export type Bullet = components["schemas"]["BulletpointRecord"];
/** The create/update body: statement text plus provenance-edge id lists. */
export type BulletWrite = components["schemas"]["BulletpointWrite"];
/** A profile source projection (role/project/certification/education). */
export type Source = components["schemas"]["SourceSummary"];
/** A worklog entry projection, offered as a provenance link in the bullet form. */
export type WorklogEntry = components["schemas"]["WorklogSummary"];
/** A reuse-list tag, offered as a search filter. */
export type Tag = components["schemas"]["TagRead"];
export type SourceKind = components["schemas"]["SourceKind"];
export type SearchLayer = components["schemas"]["SearchLayer"];
export type SearchResult = components["schemas"]["SearchResult"];

/**
 * Bullets rolled up under one source (browse mode). A bullet linked to two
 * sources appears in two groups; a bullet linked to no known source falls into
 * the synthetic "unattached" group.
 */
export interface BulletGroup {
  key: string;
  label: string;
  kind: SourceKind | null;
  bullets: Bullet[];
}

/** The bullet form's controlled values. */
export interface BulletFormValues {
  text: string;
  sourceIds: number[];
  worklogIds: number[];
}

/** Which bullet form is open: a fresh create, or an edit of a loaded bullet. */
export type LibraryEditor = { mode: "create" } | { mode: "edit"; bullet: Bullet };

/** The submitted-search lifecycle. `idle` is the browse (no query) state. */
export type SearchState =
  | { status: "idle" }
  | { status: "searching" }
  | { status: "results"; result: SearchResult }
  | { status: "error"; message: string };

/** The initial-load lifecycle for the four library datasets. */
export type DataStatus = "loading" | "ready" | "error";

export interface LibraryData {
  status: DataStatus;
  sources: Source[];
  bullets: Bullet[];
  worklogEntries: WorklogEntry[];
  tags: Tag[];
}

export interface LibraryState {
  data: LibraryData;
  query: string;
  filters: SearchFilterValues;
  search: SearchState;
  editor: LibraryEditor | null;
  /**
   * The bullet save/edit write lifecycle, scoped to the open editor session.
   * `stale` is the 409 re-read prompt; the failure message lives in the `error`
   * arm. Reset to `idle` whenever the editor opens or closes.
   */
  write: WriteState;
  archiveError: string | null;
}

export interface LibraryActions {
  setQuery: (query: string) => void;
  updateFilters: (patch: Partial<SearchFilterValues>) => void;
  submitSearch: () => void;
  clearSearch: () => void;
  openCreate: () => void;
  openEdit: (bullet: Bullet) => void;
  closeEditor: () => void;
  saveBullet: (values: BulletFormValues) => void;
  archiveBullet: (bulletId: number) => void;
  reload: () => void;
  /** Re-read the stale bullet and reopen the editor on its current revision. */
  rereadStaleBullet: () => void;
  /** Dismiss the stale-edit prompt without re-reading. */
  dismissStale: () => void;
}

export interface LibraryToolbarProps {
  query: string;
  isSearching: boolean;
  hasActiveSearch: boolean;
  onQueryChange: (query: string) => void;
  onSubmit: () => void;
  onClear: () => void;
  onNewBullet: () => void;
}

export interface FilterCheckboxOption<T extends string | number> {
  value: T;
  label: string;
}

/**
 * How a filter group renders its options: neutral checkbox rows for provenance
 * links inside a form, or pills for the search filters, where the checked pill
 * carries the accent fill.
 */
export type FilterOptionVariant = "checkbox" | "chip";

export interface FilterCheckboxGroupProps<T extends string | number> {
  legend: string;
  options: FilterCheckboxOption<T>[];
  selected: readonly T[];
  onToggle: (value: T) => void;
  /** Defaults to the neutral checkbox rows. */
  variant?: FilterOptionVariant;
}

export interface SearchFiltersProps {
  sources: Source[];
  tags: Tag[];
  filters: SearchFilterValues;
  onChange: (patch: Partial<SearchFilterValues>) => void;
}

export interface BulletRowProps {
  bullet: Bullet;
  onEdit: (bullet: Bullet) => void;
  onArchive: (bulletId: number) => void;
}

export interface BrowseGroupsProps {
  groups: BulletGroup[];
  onEdit: (bullet: Bullet) => void;
  onArchive: (bulletId: number) => void;
}

export interface BulletFormProps {
  mode: LibraryEditor["mode"];
  initialValues: BulletFormValues;
  sources: Source[];
  worklogEntries: WorklogEntry[];
  isSaving: boolean;
  error: string | null;
  onSubmit: (values: BulletFormValues) => void;
  onCancel: () => void;
}
