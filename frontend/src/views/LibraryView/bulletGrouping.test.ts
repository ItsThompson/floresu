import { describe, expect, it } from "vitest";

import { groupBulletsBySource } from "./bulletGrouping";
import { UNATTACHED_GROUP_KEY } from "./constants";
import type { Bullet, Source } from "./types";

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
