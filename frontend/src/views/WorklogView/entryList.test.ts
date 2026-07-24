import { describe, expect, it } from "vitest";

import { buildEntry } from "./test-support/fixtures";
import { filterEntries, groupEntriesByMonth } from "./entryList";
import type { WorklogFilterValues } from "./types";

const NO_FILTERS: WorklogFilterValues = { sourceId: null, tag: null, dateFrom: null, dateTo: null };

describe("filterEntries", () => {
  const entries = [
    buildEntry({ id: 1, entry_date: "2026-07-18", tags: ["backend"], source_ids: [10] }),
    buildEntry({ id: 2, entry_date: "2026-06-10", tags: ["leadership"], source_ids: [11] }),
    buildEntry({ id: 3, entry_date: "2026-05-02", tags: ["backend"], source_ids: [10, 11] }),
  ];

  it("returns everything when no filter is active", () => {
    expect(filterEntries(entries, NO_FILTERS)).toHaveLength(3);
  });

  it("narrows by source id", () => {
    const result = filterEntries(entries, { ...NO_FILTERS, sourceId: 11 });
    expect(result.map((entry) => entry.id)).toEqual([2, 3]);
  });

  it("narrows by tag", () => {
    const result = filterEntries(entries, { ...NO_FILTERS, tag: "backend" });
    expect(result.map((entry) => entry.id)).toEqual([1, 3]);
  });

  it("narrows by an inclusive date range", () => {
    const result = filterEntries(entries, {
      ...NO_FILTERS,
      dateFrom: "2026-06-01",
      dateTo: "2026-07-18",
    });
    expect(result.map((entry) => entry.id)).toEqual([1, 2]);
  });

  it("applies every active filter together", () => {
    const result = filterEntries(entries, {
      sourceId: 10,
      tag: "backend",
      dateFrom: "2026-05-01",
      dateTo: "2026-06-01",
    });
    expect(result.map((entry) => entry.id)).toEqual([3]);
  });
});

describe("groupEntriesByMonth", () => {
  it("groups by month, newest month first and newest entry first within", () => {
    const groups = groupEntriesByMonth([
      buildEntry({ id: 1, entry_date: "2026-06-10" }),
      buildEntry({ id: 2, entry_date: "2026-07-01" }),
      buildEntry({ id: 3, entry_date: "2026-07-18" }),
    ]);

    expect(groups.map((group) => group.key)).toEqual(["2026-07", "2026-06"]);
    expect(groups[0].label).toBe("July 2026");
    expect(groups[0].entries.map((entry) => entry.id)).toEqual([3, 2]);
    expect(groups[1].entries.map((entry) => entry.id)).toEqual([1]);
  });

  it("breaks a same-day tie by newest id first", () => {
    const groups = groupEntriesByMonth([
      buildEntry({ id: 5, entry_date: "2026-07-18" }),
      buildEntry({ id: 9, entry_date: "2026-07-18" }),
    ]);
    expect(groups[0].entries.map((entry) => entry.id)).toEqual([9, 5]);
  });
});
