import type { LibraryFilters, SearchLayer, SourceKind } from "./types";

/** Human labels for the four ground-truth source kinds. */
export const SOURCE_KIND_LABELS: Record<SourceKind, string> = {
  role: "Role",
  project: "Project",
  certification: "Certification",
  education: "Education",
};

/** The source-kind filter options, in a stable display order. */
export const SOURCE_KIND_OPTIONS: { value: SourceKind; label: string }[] = [
  { value: "role", label: SOURCE_KIND_LABELS.role },
  { value: "project", label: SOURCE_KIND_LABELS.project },
  { value: "certification", label: SOURCE_KIND_LABELS.certification },
  { value: "education", label: SOURCE_KIND_LABELS.education },
];

/** The searchable-layer options; `both` is the default. */
export const SEARCH_LAYER_OPTIONS: { value: SearchLayer; label: string }[] = [
  { value: "both", label: "All layers" },
  { value: "raw", label: "Raw" },
  { value: "library", label: "Library" },
];

/** Filters at rest: no narrowing, both layers. */
export const DEFAULT_FILTERS: LibraryFilters = {
  sourceIds: [],
  kinds: [],
  tags: [],
  layer: "both",
  dateFrom: "",
  dateTo: "",
};

export const UNATTACHED_GROUP_KEY = "unattached";
export const UNATTACHED_GROUP_LABEL = "Unattached";

export const LOAD_ERROR_MESSAGE = "Could not load your library.";
export const SEARCH_ERROR_MESSAGE = "Search failed. Try again.";
export const SAVE_ERROR_FALLBACK = "Could not save the bullet. Try again.";
export const ARCHIVE_ERROR_FALLBACK = "Could not archive the bullet. Try again.";
export const EMPTY_LIBRARY_MESSAGE = "No bullets yet. Write your first framing.";
export const EMPTY_SEARCH_MESSAGE = "No matches. Try a different query or fewer filters.";
