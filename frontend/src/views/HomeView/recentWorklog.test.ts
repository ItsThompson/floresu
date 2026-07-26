import { describe, expect, it } from "vitest";

import { buildEntry } from "@/mocks/worklogFixtures";

import { selectRecentWorklog } from "./recentWorklog";

describe("selectRecentWorklog", () => {
  it("orders entries newest-date first", () => {
    const entries = [
      buildEntry({ id: 1, entry_date: "2026-01-10" }),
      buildEntry({ id: 2, entry_date: "2026-07-18" }),
      buildEntry({ id: 3, entry_date: "2026-03-02" }),
    ];

    expect(selectRecentWorklog(entries, 5).map((entry) => entry.id)).toEqual([2, 3, 1]);
  });

  it("breaks same-date ties by newest id first", () => {
    const entries = [
      buildEntry({ id: 7, entry_date: "2026-07-18" }),
      buildEntry({ id: 9, entry_date: "2026-07-18" }),
      buildEntry({ id: 8, entry_date: "2026-07-18" }),
    ];

    expect(selectRecentWorklog(entries, 5).map((entry) => entry.id)).toEqual([9, 8, 7]);
  });

  it("caps the result at the preview count, keeping the newest", () => {
    const entries = Array.from({ length: 8 }, (_, index) =>
      buildEntry({ id: index + 1, entry_date: `2026-07-0${index + 1}` }),
    );

    const preview = selectRecentWorklog(entries, 5);

    expect(preview).toHaveLength(5);
    expect(preview.map((entry) => entry.id)).toEqual([8, 7, 6, 5, 4]);
  });

  it("does not mutate the input array", () => {
    const entries = [
      buildEntry({ id: 1, entry_date: "2026-01-10" }),
      buildEntry({ id: 2, entry_date: "2026-07-18" }),
    ];

    selectRecentWorklog(entries, 5);

    expect(entries.map((entry) => entry.id)).toEqual([1, 2]);
  });

  it("returns an empty array for no entries", () => {
    expect(selectRecentWorklog([], 5)).toEqual([]);
  });
});
