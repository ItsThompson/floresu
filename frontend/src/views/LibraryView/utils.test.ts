import { describe, expect, it } from "vitest";

import { DEFAULT_FILTERS, UNATTACHED_GROUP_KEY } from "./constants";
import type { Bullet, LibraryFilters, SearchResult, Source } from "./types";
import {
  buildRankedRows,
  buildSearchGroups,
  groupBulletsBySource,
  isShared,
  toSearchFilters,
  toggleValue,
  usedInLabel,
} from "./utils";

const source = (id: number, overrides: Partial<Source> = {}): Source => ({
  id,
  kind: "role",
  display_label: `Source ${id}`,
  date_start: null,
  date_end: null,
  summary: null,
  sort_order: id,
  archived_at: null,
  ...overrides,
});

const bullet = (id: number, overrides: Partial<Bullet> = {}): Bullet => ({
  id,
  text: `Bullet ${id}`,
  source_ids: [],
  worklog_ids: [],
  used_in_count: 0,
  revision: 1,
  archived_at: null,
  ...overrides,
});

describe("usedInLabel / isShared", () => {
  it("labels an unused bullet and shows no shared marker", () => {
    expect(usedInLabel(0)).toBe("Unused");
    expect(isShared(0)).toBe(false);
  });

  it("labels a single use without the shared marker", () => {
    expect(usedInLabel(1)).toBe("Used in 1");
    expect(isShared(1)).toBe(false);
  });

  it("marks a bullet shared once two or more resumes use it", () => {
    expect(usedInLabel(2)).toBe("Used in 2");
    expect(isShared(2)).toBe(true);
  });
});

describe("groupBulletsBySource", () => {
  it("groups bullets under each linked source, ordered by source sort order", () => {
    const sources = [source(2, { sort_order: 2 }), source(1, { sort_order: 1 })];
    const bullets = [bullet(10, { source_ids: [1] }), bullet(11, { source_ids: [2] })];

    const groups = groupBulletsBySource(bullets, sources);

    expect(groups.map((group) => group.key)).toEqual(["source-1", "source-2"]);
  });

  it("lists a bullet linked to two sources under both", () => {
    const sources = [source(1), source(2)];
    const shared = bullet(10, { source_ids: [1, 2] });

    const groups = groupBulletsBySource([shared], sources);

    expect(groups).toHaveLength(2);
    expect(groups[0].bullets[0].id).toBe(10);
    expect(groups[1].bullets[0].id).toBe(10);
  });

  it("collects bullets with no known source into a trailing unattached group", () => {
    const sources = [source(1)];
    const bullets = [bullet(10, { source_ids: [1] }), bullet(11, { source_ids: [] })];

    const groups = groupBulletsBySource(bullets, sources);

    const last = groups[groups.length - 1];
    expect(last.key).toBe(UNATTACHED_GROUP_KEY);
    expect(last.bullets.map((entry) => entry.id)).toEqual([11]);
  });

  it("treats a bullet linked only to an archived (unknown) source as unattached", () => {
    const sources = [source(1)];
    const orphan = bullet(11, { source_ids: [99] });

    const groups = groupBulletsBySource([orphan], sources);

    expect(groups).toHaveLength(1);
    expect(groups[0].key).toBe(UNATTACHED_GROUP_KEY);
  });

  it("omits sources that have no bullets", () => {
    const sources = [source(1), source(2)];
    const groups = groupBulletsBySource([bullet(10, { source_ids: [1] })], sources);

    expect(groups.map((group) => group.key)).toEqual(["source-1"]);
  });
});

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

describe("toggleValue", () => {
  it("adds a missing value and removes a present one", () => {
    expect(toggleValue([1, 2], 3)).toEqual([1, 2, 3]);
    expect(toggleValue([1, 2], 2)).toEqual([1]);
  });
});
