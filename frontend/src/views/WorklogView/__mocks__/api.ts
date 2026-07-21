import { http, HttpResponse } from "msw";

import { server } from "@/mocks/server";

import type {
  BulletpointRecord,
  SearchResult,
  SourceSummary,
  TagRead,
  WorklogSummary,
  WorklogWrite,
} from "../types";
import { buildEntryRecord } from "./fixtures";

interface WorklogApiOptions {
  entries?: WorklogSummary[];
  sources?: SourceSummary[];
  tags?: TagRead[];
  bullets?: BulletpointRecord[];
  search?: SearchResult;
  /** Force the timeline read to fail, exercising the error state. */
  failTimeline?: boolean;
  /** Force writes (create/edit) to fail, exercising the inline write error. */
  failWrite?: boolean;
  /** Force the search request to fail. */
  failSearch?: boolean;
}

/** Records the writes the view issued, so tests assert intent without internals. */
export interface WorklogApiCalls {
  created: WorklogWrite[];
  updated: { id: number; body: WorklogWrite }[];
  archived: number[];
  searched: string[];
}

const ARCHIVED_AT = "2026-07-21T00:00:00Z";

/**
 * Install a stateful MSW backend for the worklog endpoints on the shared test
 * server. Reads reflect prior writes (create appends, edit updates, archive
 * drops from the active list), so the timeline behaves like the real API. The
 * returned object captures the request bodies for assertions.
 */
export function installWorklogApi(options: WorklogApiOptions = {}): WorklogApiCalls {
  const entries = [...(options.entries ?? [])];
  const sources = options.sources ?? [];
  const tags = options.tags ?? [];
  const bullets = options.bullets ?? [];
  const calls: WorklogApiCalls = { created: [], updated: [], archived: [], searched: [] };
  let nextId = Math.max(0, ...entries.map((entry) => entry.id)) + 1;

  const recordFor = (entry: WorklogSummary) => buildEntryRecord({ ...entry, bullet_ids: [] });

  server.use(
    http.get("*/worklog", ({ request }) => {
      if (options.failTimeline) return new HttpResponse(null, { status: 500 });
      const includeArchived = new URL(request.url).searchParams.get("include_archived") === "true";
      return HttpResponse.json(
        entries.filter((entry) => includeArchived || entry.archived_at === null),
      );
    }),
    http.get("*/worklog/tags", () => HttpResponse.json(tags)),
    http.get("*/sources", () => HttpResponse.json(sources)),
    http.get("*/bullets", () => HttpResponse.json(bullets)),

    http.post("*/worklog", async ({ request }) => {
      if (options.failWrite) return new HttpResponse(null, { status: 500 });
      const body = (await request.json()) as WorklogWrite;
      calls.created.push(body);
      const entry: WorklogSummary = {
        id: nextId++,
        title: body.title,
        entry_date: body.entry_date,
        description: body.description ?? null,
        tags: body.tags ?? [],
        source_ids: body.source_ids ?? [],
        archived_at: null,
      };
      entries.push(entry);
      return HttpResponse.json(recordFor(entry), { status: 201 });
    }),

    http.put("*/worklog/:id", async ({ request, params }) => {
      if (options.failWrite) return new HttpResponse(null, { status: 500 });
      const id = Number(params.id);
      const body = (await request.json()) as WorklogWrite;
      calls.updated.push({ id, body });
      const index = entries.findIndex((entry) => entry.id === id);
      const updated: WorklogSummary = {
        ...entries[index],
        title: body.title,
        entry_date: body.entry_date,
        description: body.description ?? null,
        tags: body.tags ?? [],
        source_ids: body.source_ids ?? [],
      };
      entries[index] = updated;
      return HttpResponse.json(recordFor(updated));
    }),

    http.post("*/worklog/:id/archive", ({ params }) => {
      const id = Number(params.id);
      calls.archived.push(id);
      const index = entries.findIndex((entry) => entry.id === id);
      entries[index] = { ...entries[index], archived_at: ARCHIVED_AT };
      return HttpResponse.json(recordFor(entries[index]));
    }),

    http.post("*/search", async ({ request }) => {
      const body = (await request.json()) as { query: string };
      calls.searched.push(body.query);
      if (options.failSearch) return new HttpResponse(null, { status: 500 });
      return HttpResponse.json(
        options.search ?? { ranked: [], graph: { sources: [], worklog: [], bullets: [] }, notices: [] },
      );
    }),
  );

  return calls;
}
