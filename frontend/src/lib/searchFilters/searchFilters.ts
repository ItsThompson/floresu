import type { components } from "@/api";

type SearchLayer = components["schemas"]["SearchLayer"];
type SourceKind = components["schemas"]["SourceKind"];

/** The filter body `POST /search` accepts. */
export type SearchQueryFilters = components["schemas"]["SearchFilters"];

/**
 * The filter UI state every searching surface holds. The mapping onto the API
 * body is a domain rule rather than a per-view choice, so the shape and the
 * mapper live together here. A surface whose own controls are narrower (a
 * single-select) widens onto this shape before mapping.
 */
export interface SearchFilterValues {
  sourceIds: number[];
  kinds: SourceKind[];
  tags: string[];
  layer: SearchLayer;
  /** ISO date (`YYYY-MM-DD`); empty string means unset. */
  dateFrom: string;
  dateTo: string;
}

/** Filters at rest: no narrowing, both layers. */
export const DEFAULT_SEARCH_FILTERS: SearchFilterValues = {
  sourceIds: [],
  kinds: [],
  tags: [],
  layer: "both",
  dateFrom: "",
  dateTo: "",
};

/**
 * Map the local filter UI state onto the API filter body. `layer` is always
 * sent; the id/tag lists and the date range are included only when set, so an
 * unused filter never narrows the corpus.
 */
export function toSearchFilters(filters: SearchFilterValues): SearchQueryFilters {
  const result: SearchQueryFilters = { layer: filters.layer };
  if (filters.sourceIds.length > 0) result.source_ids = filters.sourceIds;
  if (filters.kinds.length > 0) result.kinds = filters.kinds;
  if (filters.tags.length > 0) result.tags = filters.tags;
  if (filters.dateFrom || filters.dateTo) {
    result.date_range = { from: filters.dateFrom || null, to: filters.dateTo || null };
  }
  return result;
}
