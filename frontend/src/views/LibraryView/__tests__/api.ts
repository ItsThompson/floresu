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
      const body = (await request.json()) as BulletWrite;
      const id = Number(params.id);
      bullets = bullets.map((entry) =>
        entry.id === id
          ? {
              ...entry,
              text: body.text,
              source_ids: body.source_ids ?? [],
              worklog_ids: body.worklog_ids ?? [],
              revision: entry.revision + 1,
            }
          : entry,
      );
      return HttpResponse.json(bullets.find((entry) => entry.id === id));
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
  };
}
