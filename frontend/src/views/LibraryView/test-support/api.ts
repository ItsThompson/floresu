import { http, HttpResponse } from "msw";

import { server } from "@/mocks/server";

import type { Bullet, BulletWrite, SearchResult, Source, Tag, WorklogEntry } from "../types";
import { buildBullet, buildSearchResult } from "./fixtures";

interface LibraryApiSeed {
  sources?: Source[];
  bullets?: Bullet[];
  worklog?: WorklogEntry[];
  tags?: Tag[];
  search?: SearchResult;
}

interface LibraryApiHandle {
  setSearchResult: (result: SearchResult) => void;
  getBullets: () => Bullet[];
  /** Simulate a concurrent writer: bump the stored revision and rewrite the text. */
  recordExternalEdit: (id: number, text: string) => void;
}

/**
 * Install stateful MSW handlers for the Library endpoints on the shared test
 * server. Writes mutate an in-memory bullet list so a create adds a row, an edit
 * rewrites one, and an archive removes it from the active list, letting a test
 * assert the same refresh-after-write the real view relies on. Matches by URL
 * (order-independent) per the mocking-by-identity convention.
 */
export function installLibraryApi(seed: LibraryApiSeed = {}): LibraryApiHandle {
  const sources = seed.sources ?? [];
  const worklog = seed.worklog ?? [];
  const tags = seed.tags ?? [];
  let bullets = seed.bullets ? [...seed.bullets] : [];
  let searchResult = seed.search ?? buildSearchResult();
  let nextId = bullets.reduce((max, entry) => Math.max(max, entry.id), 0) + 1;

  const active = (): Bullet[] => bullets.filter((entry) => entry.archived_at === null);

  server.use(
    http.get("*/sources", () => HttpResponse.json(sources)),
    http.get("*/bullets", () => HttpResponse.json(active())),
    http.get("*/bullets/:id", ({ params }) => {
      const id = Number(params.id);
      const found = bullets.find((entry) => entry.id === id);
      return found ? HttpResponse.json(found) : new HttpResponse(null, { status: 404 });
    }),
    http.get("*/worklog", () => HttpResponse.json(worklog)),
    http.get("*/worklog/tags", () => HttpResponse.json(tags)),
    http.post("*/search", () => HttpResponse.json(searchResult)),
    http.post("*/bullets", async ({ request }) => {
      const body = (await request.json()) as BulletWrite;
      const created = buildBullet({
        id: nextId++,
        text: body.text,
        source_ids: body.source_ids ?? [],
        worklog_ids: body.worklog_ids ?? [],
        used_in_count: 0,
      });
      bullets.push(created);
      return HttpResponse.json(created, { status: 201 });
    }),
    http.put("*/bullets/:id", async ({ request, params }) => {
      const id = Number(params.id);
      const current = bullets.find((entry) => entry.id === id);
      if (!current) return new HttpResponse(null, { status: 404 });
      // Mirror the backend CAS: the write only lands when the loaded revision
      // still matches, otherwise it is a recoverable 409 (no overwrite).
      const ifMatch = Number(request.headers.get("If-Match"));
      if (current.revision !== ifMatch) {
        return HttpResponse.json(
          { detail: "This bulletpoint changed since you loaded it; re-read and retry." },
          { status: 409 },
        );
      }
      const body = (await request.json()) as BulletWrite;
      const updated: Bullet = {
        ...current,
        text: body.text,
        source_ids: body.source_ids ?? [],
        worklog_ids: body.worklog_ids ?? [],
        revision: current.revision + 1,
      };
      bullets = bullets.map((entry) => (entry.id === id ? updated : entry));
      return HttpResponse.json(updated);
    }),
    http.post("*/bullets/:id/archive", ({ params }) => {
      const id = Number(params.id);
      let archived: Bullet | undefined;
      bullets = bullets.map((entry) => {
        if (entry.id !== id) return entry;
        archived = { ...entry, archived_at: "2026-07-21T00:00:00Z" };
        return archived;
      });
      return HttpResponse.json(archived);
    }),
  );

  return {
    setSearchResult: (result) => {
      searchResult = result;
    },
    getBullets: () => bullets,
    recordExternalEdit: (id, text) => {
      bullets = bullets.map((entry) =>
        entry.id === id ? { ...entry, text, revision: entry.revision + 1 } : entry,
      );
    },
  };
}
