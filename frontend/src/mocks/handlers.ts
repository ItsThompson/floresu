import { delay, http, HttpResponse } from "msw";

import { mockAuthUser } from "./data";

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
];
