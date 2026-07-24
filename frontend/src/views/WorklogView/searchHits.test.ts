import { describe, expect, it } from "vitest";

import { buildSearchResult } from "./test-support/fixtures";
import { resolveRankedHits } from "./searchHits";

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
