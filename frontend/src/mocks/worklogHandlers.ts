import { delay, http, HttpResponse } from "msw";

import type { components } from "@/api";

import {
  buildBullet,
  buildEntry,
  buildEntryRecord,
  buildSearchResult,
  buildSource,
  buildTag,
} from "./worklogFixtures";

/**
 * Dev-harness MSW handlers for the worklog screen (`npm run dev:mock`). Kept in
 * their own module so the shared `handlers.ts` only spreads them in. State is
 * module-level and per page load: create, edit, and archive mutate it so the
 * timeline reflects writes, matching the real API closely enough to click
 * through the screen without a backend.
 */

type WorklogSummary = components["schemas"]["WorklogSummary"];
type WorklogRecord = components["schemas"]["WorklogRecord"];
type WorklogWrite = components["schemas"]["WorklogWrite"];
type SourceSummary = components["schemas"]["SourceSummary"];
type TagRead = components["schemas"]["TagRead"];
type BulletpointRecord = components["schemas"]["BulletpointRecord"];

const LATENCY_MS = 120;

const sources: SourceSummary[] = [
  buildSource({ id: 10 }),
  buildSource({ id: 11, kind: "project", display_label: "Floresu", date_start: "2025-06-01", sort_order: 1 }),
];

const tags: TagRead[] = [
  buildTag({ id: 1, label: "backend" }),
  buildTag({ id: 2, label: "payments" }),
  buildTag({ id: 3, label: "leadership" }),
];

// The dev harness deliberately shows a shorter entry description and a higher
// bullet reuse count than the canonical builder defaults. Both are explicit
// overrides so the data keeps one shape with visible, intentional deviations.
const bullets: BulletpointRecord[] = [buildBullet({ used_in_count: 2 })];

let entries: WorklogSummary[] = [
  buildEntry({ id: 1, description: "Zero-downtime cutover." }),
  buildEntry({
    id: 2,
    title: "Fixed cache invalidation bug",
    entry_date: "2026-07-04",
    description: null,
    tags: ["backend"],
  }),
  buildEntry({
    id: 3,
    title: "Led cross-team API redesign",
    entry_date: "2026-06-20",
    description: null,
    tags: ["leadership"],
    source_ids: [10, 11],
  }),
];
let nextId = 4;

const recordFor = (entry: WorklogSummary): WorklogRecord =>
  buildEntryRecord({ ...entry, bullet_ids: entry.id === 1 ? [100] : [] });

export const worklogHandlers = [
  http.get("*/worklog", async ({ request }) => {
    await delay(LATENCY_MS);
    const includeArchived = new URL(request.url).searchParams.get("include_archived") === "true";
    return HttpResponse.json(entries.filter((entry) => includeArchived || entry.archived_at === null));
  }),
  http.get("*/worklog/tags", () => HttpResponse.json(tags)),
  http.get("*/sources", () => HttpResponse.json(sources)),
  http.get("*/bullets", () => HttpResponse.json(bullets)),

  http.post("*/worklog", async ({ request }) => {
    const body = (await request.json()) as WorklogWrite;
    const entry: WorklogSummary = {
      id: nextId++,
      title: body.title,
      entry_date: body.entry_date,
      description: body.description ?? null,
      tags: body.tags ?? [],
      source_ids: body.source_ids ?? [],
      archived_at: null,
    };
    entries = [...entries, entry];
    return HttpResponse.json(recordFor(entry), { status: 201 });
  }),

  http.put("*/worklog/:id", async ({ request, params }) => {
    const id = Number(params.id);
    const body = (await request.json()) as WorklogWrite;
    entries = entries.map((entry) =>
      entry.id === id
        ? { ...entry, title: body.title, entry_date: body.entry_date, description: body.description ?? null, tags: body.tags ?? [], source_ids: body.source_ids ?? [] }
        : entry,
    );
    return HttpResponse.json(recordFor(entries.find((entry) => entry.id === id)!));
  }),

  http.post("*/worklog/:id/archive", ({ params }) => {
    const id = Number(params.id);
    entries = entries.map((entry) => (entry.id === id ? { ...entry, archived_at: "2026-07-21T00:00:00Z" } : entry));
    return HttpResponse.json(recordFor(entries.find((entry) => entry.id === id)!));
  }),

  http.post("*/search", async ({ request }) => {
    const { query } = (await request.json()) as { query: string };
    await delay(LATENCY_MS);
    const [entry] = entries;
    const [bullet] = bullets;
    const [source] = sources;
    return HttpResponse.json(
      buildSearchResult({
        ranked: [
          { type: "worklog", id: entry.id, score: 0.92 },
          { type: "bullet", id: bullet.id, score: 0.61 },
          { type: "source", id: source.id, score: 0.4 },
        ],
        graph: {
          worklog: [
            {
              id: entry.id,
              title: `${entry.title} (${query})`,
              date: entry.entry_date,
              score: 0.92,
              source_ids: entry.source_ids,
            },
          ],
          bullets: [
            {
              id: bullet.id,
              text: bullet.text,
              score: 0.61,
              worklog_ids: bullet.worklog_ids,
              source_ids: bullet.source_ids,
            },
          ],
          sources: [
            { id: source.id, kind: source.kind, label: source.display_label, match_score: 0.4, score: 0.4 },
          ],
        },
      }),
    );
  }),
];
