import type { LibraryFilters, SearchQueryFilters } from "./types";

/**
 * Map the local filter UI state onto the API filter body. `layer` is always
 * sent; the id/tag lists and the date range are included only when set, so an
 * unused filter never narrows the corpus.
 */
export function toSearchFilters(filters: LibraryFilters): SearchQueryFilters {
  const result: SearchQueryFilters = { layer: filters.layer };
  if (filters.sourceIds.length > 0) result.source_ids = filters.sourceIds;
  if (filters.kinds.length > 0) result.kinds = filters.kinds;
  if (filters.tags.length > 0) result.tags = filters.tags;
  if (filters.dateFrom || filters.dateTo) {
    result.date_range = { from: filters.dateFrom || null, to: filters.dateTo || null };
  }
  return result;
}
