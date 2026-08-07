import { describe, expect, it } from "vitest";

import { DEFAULT_SEARCH_FILTERS, toSearchFilters } from "./searchFilters";
import type { SearchFilterValues } from "./searchFilters";

describe("toSearchFilters", () => {
  it("always sends the layer and omits empty narrowing filters", () => {
    expect(toSearchFilters(DEFAULT_SEARCH_FILTERS)).toEqual({ layer: "both" });
  });

  it("includes only the filters that are set", () => {
    const filters: SearchFilterValues = {
      sourceIds: [1],
      kinds: ["role"],
      tags: ["backend"],
      layer: "library",
      dateFrom: "2026-01-01",
      dateTo: "",
    };
    expect(toSearchFilters(filters)).toEqual({
      layer: "library",
      source_ids: [1],
      kinds: ["role"],
      tags: ["backend"],
      date_range: { from: "2026-01-01", to: null },
    });
  });
});
