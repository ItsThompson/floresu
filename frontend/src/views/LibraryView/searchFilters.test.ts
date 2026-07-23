import { describe, expect, it } from "vitest";

import { DEFAULT_FILTERS } from "./constants";
import { toSearchFilters } from "./searchFilters";
import type { LibraryFilters } from "./types";

describe("toSearchFilters", () => {
  it("always sends the layer and omits empty narrowing filters", () => {
    expect(toSearchFilters(DEFAULT_FILTERS)).toEqual({ layer: "both" });
  });

  it("includes only the filters that are set", () => {
    const filters: LibraryFilters = {
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
