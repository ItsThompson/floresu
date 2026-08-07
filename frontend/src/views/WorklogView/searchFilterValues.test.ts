import { describe, expect, it } from "vitest";

import { toSearchFilterValues } from "./searchFilterValues";
import type { WorklogFilterValues } from "./types";

const NO_FILTERS: WorklogFilterValues = {
  sourceId: null,
  tag: null,
  dateFrom: null,
  dateTo: null,
};

describe("toSearchFilterValues", () => {
  it("maps an unfiltered timeline onto filters at rest", () => {
    expect(toSearchFilterValues(NO_FILTERS)).toEqual({
      sourceIds: [],
      kinds: [],
      tags: [],
      layer: "both",
      dateFrom: "",
      dateTo: "",
    });
  });

  it("widens the single-select source and tag onto their list counterparts", () => {
    const widened = toSearchFilterValues({ ...NO_FILTERS, sourceId: 10, tag: "backend" });

    expect(widened.sourceIds).toEqual([10]);
    expect(widened.tags).toEqual(["backend"]);
  });

  it("carries a half-open date range across as an empty bound", () => {
    const widened = toSearchFilterValues({ ...NO_FILTERS, dateFrom: "2026-07-01" });

    expect(widened.dateFrom).toBe("2026-07-01");
    expect(widened.dateTo).toBe("");
  });
});
