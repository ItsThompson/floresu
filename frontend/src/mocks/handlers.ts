import { delay, http, HttpResponse } from "msw";

import {
  buildBullet,
  buildSkill,
  buildSourceRecord,
  buildSourceSummary,
  buildVariant,
  buildWorklogSummary,
  mockAuthUser,
  mockFeedHistory,
} from "./data";
import { worklogHandlers } from "./worklogHandlers";

/**
 * MSW request handlers for the zero-backend dev harness (`npm run dev:mock`).
 * Paths are prefixed with `*` so they match regardless of the client's API base
 * URL (relative in dev, absolute against the API subdomain in prod).
 *
 * The harness starts anonymous: refresh has no session to resume. Register and
 * login return the demo user so the authenticated shell can be exercised without
 * a backend. A modest fixed latency lets loading states render realistically.
 */
const LATENCY_MS = 120;

export const handlers = [
  http.post("*/auth/refresh", () => new HttpResponse(null, { status: 401 })),

  http.post("*/auth/register", async () => {
    await delay(LATENCY_MS);
    return HttpResponse.json(mockAuthUser, { status: 201 });
  }),

  http.post("*/auth/login", async () => {
    await delay(LATENCY_MS);
    return HttpResponse.json(mockAuthUser);
  }),

  http.post("*/auth/logout", () => new HttpResponse(null, { status: 204 })),

  http.get("*/me", async () => {
    await delay(LATENCY_MS);
    return HttpResponse.json(mockAuthUser);
  }),

  http.get("*/feed/history", async () => {
    await delay(LATENCY_MS);
    return HttpResponse.json(mockFeedHistory);
  }),

  ...worklogHandlers,

  // --- Career Profile dev-harness handlers -------------------------------
  // Read handlers return demo data; write handlers echo a plausible success so
  // the views are exercisable without a backend. They are not stateful.
  http.get("*/sources", async () => {
    await delay(LATENCY_MS);
    return HttpResponse.json([
      buildSourceSummary({ id: 100, kind: "role", display_label: "Acme — Engineer" }),
      buildSourceSummary({ id: 101, kind: "project", display_label: "StudyBoost", date_end: "2024-06-01" }),
      buildSourceSummary({ id: 102, kind: "education", display_label: "BSc CS, Bath" }),
    ]);
  }),
  http.post("*/sources", async () => HttpResponse.json(buildSourceRecord(), { status: 201 })),
  http.post("*/sources/reorder", async () => HttpResponse.json([])),
  http.get("*/sources/:id", async ({ params }) =>
    HttpResponse.json(buildSourceRecord({ id: Number(params.id) })),
  ),
  http.put("*/sources/:id", async ({ params }) =>
    HttpResponse.json(buildSourceRecord({ id: Number(params.id) })),
  ),
  http.post("*/sources/:id/archive", async ({ params }) =>
    HttpResponse.json(buildSourceRecord({ id: Number(params.id), archived_at: "2026-07-21T00:00:00Z" })),
  ),
  http.get("*/skills", async () => {
    await delay(LATENCY_MS);
    return HttpResponse.json([
      buildSkill({ id: 200, name: "React", usage_count: 4, sort_order: 0 }),
      buildSkill({ id: 201, name: "TypeScript", usage_count: 2, sort_order: 1 }),
    ]);
  }),
  http.post("*/skills", async () => HttpResponse.json(buildSkill({ id: 299 }), { status: 201 })),
  http.post("*/skills/reorder", async () => HttpResponse.json([])),
  http.put("*/skills/:id", async ({ params }) =>
    HttpResponse.json(buildSkill({ id: Number(params.id) })),
  ),
  http.post("*/skills/:id/archive", async ({ params }) =>
    HttpResponse.json(buildSkill({ id: Number(params.id), archived_at: "2026-07-21T00:00:00Z" })),
  ),
  http.get("*/identity-variants", async () => {
    await delay(LATENCY_MS);
    return HttpResponse.json([buildVariant({ id: 300, label: "Default", is_default: true })]);
  }),
  http.post("*/identity-variants", async () => HttpResponse.json(buildVariant({ id: 399 }), { status: 201 })),
  http.put("*/identity-variants/:id", async ({ params }) =>
    HttpResponse.json(buildVariant({ id: Number(params.id) })),
  ),
  http.post("*/identity-variants/:id/archive", async ({ params }) =>
    HttpResponse.json(buildVariant({ id: Number(params.id), archived_at: "2026-07-21T00:00:00Z" })),
  ),
  http.get("*/bullets", async () => HttpResponse.json([buildBullet()])),
  http.post("*/bullets", async () => HttpResponse.json(buildBullet({ id: 499 }), { status: 201 })),
  http.get("*/worklog", async () => HttpResponse.json([buildWorklogSummary()])),
  http.post("*/worklog", async () =>
    HttpResponse.json({ ...buildWorklogSummary({ id: 599 }), bullet_ids: [] }, { status: 201 }),
  ),
];
