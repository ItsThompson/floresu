import { describe, expect, it } from "vitest";

import { buildEntry, buildSearchResult, buildSource } from "./__mocks__/fixtures";
import type { WorklogFilterValues } from "./types";
import {
  filterEntries,
  formatDayLabel,
  formatMonthLabel,
  groupEntriesByMonth,
  resolveRankedHits,
  sourceLabel,
} from "./utils";

const NO_FILTERS: WorklogFilterValues = { sourceId: null, tag: null, dateFrom: null, dateTo: null };

describe("formatMonthLabel / formatDayLabel", () => {
  it("formats a calendar date in UTC without a timezone off-by-one", () => {
    expect(formatMonthLabel("2026-07-01")).toBe("July 2026");
    expect(formatDayLabel("2026-07-18")).toBe("Jul 18");
    // The first of the month must not slip to the previous month/day.
    expect(formatDayLabel("2026-01-01")).toBe("Jan 01");
  });
});

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

describe("sourceLabel", () => {
  const sources = [buildSource({ id: 10, display_label: "Acme — Senior Engineer" })];

  it("returns the display label for a known source", () => {
    expect(sourceLabel(sources, 10)).toBe("Acme — Senior Engineer");
  });

  it("falls back to a stable placeholder for an unknown source", () => {
    expect(sourceLabel(sources, 99)).toBe("Source 99");
  });
});

describe("resolveRankedHits", () => {
  it("joins each ranked hit to its graph node, preserving the fused order", () => {
    const result = buildSearchResult({
      ranked: [
        { type: "worklog", id: 1, score: 0.9 },
        { type: "bullet", id: 100, score: 0.5 },
        { type: "source", id: 10, score: 0.3 },
      ],
      graph: {
        sources: [{ id: 10, kind: "role", label: "Acme", match_score: 0.3, score: 0.3 }],
        worklog: [{ id: 1, title: "Shipped payments", date: "2026-07-18", score: 0.9, source_ids: [10] }],
        bullets: [{ id: 100, text: "Cut latency 40%", score: 0.5, worklog_ids: [1], source_ids: [10] }],
      },
    });

    const resolved = resolveRankedHits(result);

    expect(resolved.map((hit) => [hit.type, hit.label])).toEqual([
      ["worklog", "Shipped payments"],
      ["bullet", "Cut latency 40%"],
      ["source", "Acme"],
    ]);
    expect(resolved[0].detail).toBe("Jul 18");
    expect(resolved[2].detail).toBe("role");
  });

  it("drops a ranked hit that has no matching graph node", () => {
    const result = buildSearchResult({
      ranked: [{ type: "worklog", id: 42, score: 0.9 }],
    });
    expect(resolveRankedHits(result)).toEqual([]);
  });
});
