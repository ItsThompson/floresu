import { describe, expect, it } from "vitest";

import { buildSearchGroups } from "./sourceGroups";
import type { SearchGraph } from "./sourceGroups";

const searchGraph = (): SearchGraph => ({
  sources: [
    { id: 1, kind: "role", label: "Acme", match_score: 0.9, score: 0.95 },
    { id: 2, kind: "project", label: "Floresu", score: 0.4 },
  ],
  worklog: [{ id: 30, title: "Shipped payments", date: "2026-07-18", score: 0.5, source_ids: [1] }],
  bullets: [
    { id: 20, text: "Cut latency 40%", score: 0.7, worklog_ids: [30], source_ids: [] },
    { id: 21, text: "Owned Stripe", score: 0.3, worklog_ids: [], source_ids: [2] },
  ],
});

describe("buildSearchGroups", () => {
  it("orders groups by source score, highest first", () => {
    const groups = buildSearchGroups(searchGraph());
    expect(groups.map((group) => group.id)).toEqual([1, 2]);
  });

  it("attaches worklog directly linked to the source and reports a direct match", () => {
    const groups = buildSearchGroups(searchGraph());
    const acme = groups.find((group) => group.id === 1);
    expect(acme?.matchScore).toBe(0.9);
    expect(acme?.worklog.map((entry) => entry.id)).toEqual([30]);
  });

  it("reconstructs the source→worklog→bullet chain for a bullet with no direct source edge", () => {
    const groups = buildSearchGroups(searchGraph());
    const acme = groups.find((group) => group.id === 1);
    // Bullet 20 links to worklog 30 (not to source 1 directly) yet rolls up here.
    expect(acme?.bullets.map((entry) => entry.id)).toEqual([20]);
  });

  it("leaves matchScore null for a source that only has matching children", () => {
    const groups = buildSearchGroups(searchGraph());
    const floresu = groups.find((group) => group.id === 2);
    expect(floresu?.matchScore).toBeNull();
    expect(floresu?.bullets.map((entry) => entry.id)).toEqual([21]);
  });
});
