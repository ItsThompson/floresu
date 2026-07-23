import { describe, expect, it } from "vitest";

import type { SessionClient } from "@/api";
import { buildBullet, buildSourceSummary, buildWorklogSummary } from "@/mocks/data";

import type { ArchivedEntityType, ArchivedItem } from "../types";
import { deleteArchivedItem, loadArchivedItems, restoreArchivedItem } from "./archiveApi";

/**
 * Direct route-dispatch tests for the pure boundary module. Each function takes
 * the client as an argument, so a hand-rolled stub that records every call lets
 * us assert the exact openapi path template and typed params with no MSW,
 * provider, router, or DOM. The precedent for injected fakes is
 * `useActivityFeed.test.ts`; MSW here is reserved for provider-mounted tests and
 * cannot see which typed template was called (it matches only the resolved URL).
 */

type ClientMethod = "GET" | "POST" | "DELETE";

interface RecordedCall {
  method: ClientMethod;
  path: string;
  params?: {
    path?: Record<string, unknown>;
    query?: Record<string, unknown>;
  };
}

interface StubResult {
  data?: unknown;
  error?: unknown;
}

/**
 * Build a client that records `{ method, path, params }` per call and answers
 * from a per-route response map keyed by `"<METHOD> <template>"`. Unmapped calls
 * resolve to `{}` (no data, no error). The single `as unknown as SessionClient`
 * cast is the one boundary seam: the module only reaches for `GET`/`POST`/
 * `DELETE`, but the generated `Client<paths>` type declares many more methods
 * than a test needs to implement.
 */
function createClientStub(responses: Record<string, StubResult> = {}) {
  const calls: RecordedCall[] = [];
  const record =
    (method: ClientMethod) =>
    (path: string, options?: { params?: RecordedCall["params"] }) => {
      calls.push({ method, path, params: options?.params });
      return Promise.resolve(responses[`${method} ${path}`] ?? {});
    };
  const client = {
    GET: record("GET"),
    POST: record("POST"),
    DELETE: record("DELETE"),
  } as unknown as SessionClient;
  return { client, calls };
}

function findCall(calls: RecordedCall[], method: ClientMethod, path: string): RecordedCall | undefined {
  return calls.find((call) => call.method === method && call.path === path);
}

function archivedItem(entityType: ArchivedEntityType, id: number): ArchivedItem {
  return { entityType, id, label: "Archived item", archivedAt: "2026-07-02T00:00:00Z" };
}

const emptyLists: Record<string, StubResult> = {
  "GET /worklog": { data: [] },
  "GET /sources": { data: [] },
  "GET /bullets": { data: [] },
};

describe("loadArchivedItems", () => {
  it("reads each domain once with include_archived, matched by route identity", async () => {
    const { client, calls } = createClientStub(emptyLists);

    await loadArchivedItems(client);

    for (const path of ["/worklog", "/sources", "/bullets"]) {
      const call = findCall(calls, "GET", path);
      expect(call).toBeDefined();
      expect(call?.params?.query?.include_archived).toBe(true);
    }
  });

  it("keeps only archived rows and maps label, entityType, and archivedAt per domain", async () => {
    const { client } = createClientStub({
      "GET /worklog": {
        data: [
          buildWorklogSummary({ id: 1, title: "Archived entry", archived_at: "2026-07-02T00:00:00Z" }),
          buildWorklogSummary({ id: 2, title: "Active entry", archived_at: null }),
        ],
      },
      "GET /sources": {
        data: [
          buildSourceSummary({ id: 10, display_label: "Archived source", archived_at: "2026-07-03T00:00:00Z" }),
          buildSourceSummary({ id: 11, display_label: "Active source", archived_at: null }),
        ],
      },
      "GET /bullets": {
        data: [
          buildBullet({ id: 20, text: "Archived bullet", archived_at: "2026-07-04T00:00:00Z" }),
          buildBullet({ id: 21, text: "Active bullet", archived_at: null }),
        ],
      },
    });

    const items = await loadArchivedItems(client);

    // The three `archived_at: null` rows are excluded; the surviving rows carry
    // the numeric id and the domain-specific label field.
    expect(items).toEqual([
      { entityType: "worklog", id: 1, label: "Archived entry", archivedAt: "2026-07-02T00:00:00Z" },
      { entityType: "source", id: 10, label: "Archived source", archivedAt: "2026-07-03T00:00:00Z" },
      { entityType: "bullet", id: 20, label: "Archived bullet", archivedAt: "2026-07-04T00:00:00Z" },
    ]);
  });

  it.each(["/worklog", "/sources", "/bullets"])(
    "throws 'archive load failed' when the %s domain returns an error",
    async (failingPath) => {
      const { client } = createClientStub({
        ...emptyLists,
        [`GET ${failingPath}`]: { error: { detail: "boom" } },
      });

      await expect(loadArchivedItems(client)).rejects.toThrow("archive load failed");
    },
  );
});

describe("restoreArchivedItem", () => {
  it.each([
    ["worklog", "/worklog/{worklog_id}/restore", "worklog_id"],
    ["source", "/sources/{source_id}/restore", "source_id"],
    ["bullet", "/bullets/{bullet_id}/restore", "bullet_id"],
  ] as const)("restores a %s via POST %s with the numeric path param", async (entityType, template, paramKey) => {
    const { client, calls } = createClientStub();

    await restoreArchivedItem(client, archivedItem(entityType, 7));

    const call = findCall(calls, "POST", template);
    expect(call).toBeDefined();
    expect(call?.params?.path?.[paramKey]).toBe(7);
  });

  it("throws 'restore failed' when the restore call errors", async () => {
    const { client } = createClientStub({
      "POST /worklog/{worklog_id}/restore": { error: { detail: "nope" } },
    });

    await expect(restoreArchivedItem(client, archivedItem("worklog", 1))).rejects.toThrow("restore failed");
  });
});

describe("deleteArchivedItem", () => {
  it.each([
    ["worklog", "/worklog/{worklog_id}", "worklog_id"],
    ["source", "/sources/{source_id}", "source_id"],
    ["bullet", "/bullets/{bullet_id}", "bullet_id"],
  ] as const)(
    "deletes a %s via DELETE %s with the numeric path param and confirm:true",
    async (entityType, template, paramKey) => {
      const { client, calls } = createClientStub();

      await deleteArchivedItem(client, archivedItem(entityType, 7));

      const call = findCall(calls, "DELETE", template);
      expect(call).toBeDefined();
      expect(call?.params?.path?.[paramKey]).toBe(7);
      expect(call?.params?.query?.confirm).toBe(true);
    },
  );

  it("throws 'delete failed' when the delete call errors", async () => {
    const { client } = createClientStub({
      "DELETE /worklog/{worklog_id}": { error: { detail: "nope" } },
    });

    await expect(deleteArchivedItem(client, archivedItem("worklog", 1))).rejects.toThrow("delete failed");
  });
});
