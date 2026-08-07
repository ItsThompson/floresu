import { DEFAULT_SEARCH_FILTERS } from "@/lib/searchFilters";
import type { SearchFilterValues } from "@/lib/searchFilters";

import type { WorklogFilterValues } from "./types";

/**
 * Widen the timeline's single-select filter bar onto the shared search filter
 * shape, so the same filters that narrow the timeline also narrow a search over
 * it. The timeline offers no kind or layer control, so those stay at rest.
 */
export function toSearchFilterValues(filters: WorklogFilterValues): SearchFilterValues {
  return {
    ...DEFAULT_SEARCH_FILTERS,
    sourceIds: filters.sourceId === null ? [] : [filters.sourceId],
    tags: filters.tag === null ? [] : [filters.tag],
    dateFrom: filters.dateFrom ?? "",
    dateTo: filters.dateTo ?? "",
  };
}
