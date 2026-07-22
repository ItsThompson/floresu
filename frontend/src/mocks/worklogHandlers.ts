import { delay, http, HttpResponse } from "msw";

import type { components } from "@/api";

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
type SearchResult = components["schemas"]["SearchResult"];

const LATENCY_MS = 120;

const sources: SourceSummary[] = [
  { id: 10, kind: "role", display_label: "Acme — Senior Engineer", date_start: "2024-01-01", date_end: null, summary: null, sort_order: 0, archived_at: null },
  { id: 11, kind: "project", display_label: "Floresu", date_start: "2025-06-01", date_end: null, summary: null, sort_order: 1, archived_at: null },
];

const tags: TagRead[] = [
  { id: 1, label: "backend" },
  { id: 2, label: "payments" },
  { id: 3, label: "leadership" },
];

const bullets: BulletpointRecord[] = [
  { id: 100, text: "Cut checkout latency 40% by batching writes", source_ids: [10], worklog_ids: [1], used_in_count: 2, revision: 1, archived_at: null },
];

let entries: WorklogSummary[] = [
  { id: 1, title: "Shipped payments migration", entry_date: "2026-07-18", description: "Zero-downtime cutover.", tags: ["backend", "payments"], source_ids: [10], archived_at: null },
  { id: 2, title: "Fixed cache invalidation bug", entry_date: "2026-07-04", description: null, tags: ["backend"], source_ids: [10], archived_at: null },
  { id: 3, title: "Led cross-team API redesign", entry_date: "2026-06-20", description: null, tags: ["leadership"], source_ids: [10, 11], archived_at: null },
];
let nextId = 4;

const recordFor = (entry: WorklogSummary): WorklogRecord => ({ ...entry, bullet_ids: entry.id === 1 ? [100] : [] });

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
    const result: SearchResult = {
      ranked: [
        { type: "worklog", id: 1, score: 0.92 },
        { type: "bullet", id: 100, score: 0.61 },
        { type: "source", id: 10, score: 0.4 },
      ],
      graph: {
        worklog: [{ id: 1, title: `Shipped payments migration (${query})`, date: "2026-07-18", score: 0.92, source_ids: [10] }],
        bullets: [{ id: 100, text: "Cut checkout latency 40% by batching writes", score: 0.61, worklog_ids: [1], source_ids: [10] }],
        sources: [{ id: 10, kind: "role", label: "Acme — Senior Engineer", match_score: 0.4, score: 0.4 }],
      },
      notices: [],
    };
    return HttpResponse.json(result);
  }),
];
