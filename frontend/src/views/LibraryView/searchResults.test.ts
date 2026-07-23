import { describe, expect, it } from "vitest";

import { buildRankedRows, buildSearchGroups } from "./searchResults";
import type { SearchResult } from "./types";

const searchResult = (): SearchResult => ({
  ranked: [
    { type: "source", id: 1, score: 0.9 },
    { type: "bullet", id: 20, score: 0.7 },
    { type: "worklog", id: 30, score: 0.5 },
  ],
  graph: {
    sources: [
      { id: 1, kind: "role", label: "Acme", match_score: 0.9, score: 0.95 },
      { id: 2, kind: "project", label: "Floresu", score: 0.4 },
    ],
    worklog: [
      { id: 30, title: "Shipped payments", date: "2026-07-18", score: 0.5, source_ids: [1] },
    ],
    bullets: [
      { id: 20, text: "Cut latency 40%", score: 0.7, worklog_ids: [30], source_ids: [] },
      { id: 21, text: "Owned Stripe", score: 0.3, worklog_ids: [], source_ids: [2] },
    ],
  },
  notices: [],
});

describe("buildSearchGroups", () => {
  it("orders groups by source score, highest first", () => {
    const groups = buildSearchGroups(searchResult().graph);
    expect(groups.map((group) => group.id)).toEqual([1, 2]);
  });

  it("attaches worklog directly linked to the source and reports a direct match", () => {
    const groups = buildSearchGroups(searchResult().graph);
    const acme = groups.find((group) => group.id === 1);
    expect(acme?.matchScore).toBe(0.9);
    expect(acme?.worklog.map((entry) => entry.id)).toEqual([30]);
  });

  it("reconstructs the source→worklog→bullet chain for a bullet with no direct source edge", () => {
    const groups = buildSearchGroups(searchResult().graph);
    const acme = groups.find((group) => group.id === 1);
    // Bullet 20 links to worklog 30 (not to source 1 directly) yet rolls up here.
    expect(acme?.bullets.map((entry) => entry.id)).toEqual([20]);
  });

  it("leaves matchScore null for a source that only has matching children", () => {
    const groups = buildSearchGroups(searchResult().graph);
    const floresu = groups.find((group) => group.id === 2);
    expect(floresu?.matchScore).toBeNull();
    expect(floresu?.bullets.map((entry) => entry.id)).toEqual([21]);
  });
});

describe("buildRankedRows", () => {
  it("resolves each ranked hit's label from the matching graph node", () => {
    const rows = buildRankedRows(searchResult());
    expect(rows).toEqual([
      { key: "source-1", type: "source", label: "Acme", score: 0.9 },
      { key: "bullet-20", type: "bullet", label: "Cut latency 40%", score: 0.7 },
      { key: "worklog-30", type: "worklog", label: "Shipped payments", score: 0.5 },
    ]);
  });

  it("keeps a hit whose graph node is missing, labeled by id", () => {
    const result = searchResult();
    result.ranked = [{ type: "bullet", id: 999, score: 0.1 }];
    const rows = buildRankedRows(result);
    expect(rows[0].label).toBe("#999");
  });
});
