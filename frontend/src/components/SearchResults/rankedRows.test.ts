import { describe, expect, it } from "vitest";

import { buildRankedRows } from "./rankedRows";
import type { SearchResult } from "./rankedRows";

const searchResult = (): SearchResult => ({
  ranked: [
    { type: "source", id: 1, score: 0.9 },
    { type: "bullet", id: 20, score: 0.7 },
    { type: "worklog", id: 30, score: 0.5 },
  ],
  graph: {
    sources: [{ id: 1, kind: "role", label: "Acme", match_score: 0.9, score: 0.95 }],
    worklog: [
      { id: 30, title: "Shipped payments", date: "2026-07-18", score: 0.5, source_ids: [1] },
    ],
    bullets: [{ id: 20, text: "Cut latency 40%", score: 0.7, worklog_ids: [30], source_ids: [] }],
  },
  notices: [],
});

describe("buildRankedRows", () => {
  it("resolves each ranked hit's label and secondary detail from the matching graph node", () => {
    const rows = buildRankedRows(searchResult());
    expect(rows).toEqual([
      {
        key: "source-1",
        id: 1,
        type: "source",
        label: "Acme",
        detail: { text: "Role", dateTime: null },
        score: 0.9,
      },
      {
        key: "bullet-20",
        id: 20,
        type: "bullet",
        label: "Cut latency 40%",
        detail: null,
        score: 0.7,
      },
      {
        key: "worklog-30",
        id: 30,
        type: "worklog",
        label: "Shipped payments",
        detail: { text: "Jul 18", dateTime: "2026-07-18" },
        score: 0.5,
      },
    ]);
  });

  it("keeps a hit whose graph node is missing, labeled by id and with no detail", () => {
    const result = searchResult();
    result.ranked = [
      { type: "worklog", id: 997, score: 0.3 },
      { type: "source", id: 998, score: 0.2 },
      { type: "bullet", id: 999, score: 0.1 },
    ];
    expect(buildRankedRows(result)).toEqual([
      { key: "worklog-997", id: 997, type: "worklog", label: "#997", detail: null, score: 0.3 },
      { key: "source-998", id: 998, type: "source", label: "#998", detail: null, score: 0.2 },
      { key: "bullet-999", id: 999, type: "bullet", label: "#999", detail: null, score: 0.1 },
    ]);
  });
});
