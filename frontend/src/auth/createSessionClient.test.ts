import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { mockAuthUser } from "@/mocks/data";
import { server } from "@/mocks/server";

import { createSessionClient } from "./createSessionClient";

describe("createSessionClient", () => {
  it("refreshes once on a 401 and retries the original request", async () => {
    let meCalls = 0;
    let refreshCalls = 0;
    server.use(
      http.get("*/me", () => {
        meCalls += 1;
        return meCalls === 1 ? new HttpResponse(null, { status: 401 }) : HttpResponse.json(mockAuthUser);
      }),
      http.post("*/auth/refresh", () => {
        refreshCalls += 1;
        return new HttpResponse(null, { status: 200 });
      }),
    );

    const client = createSessionClient("http://localhost");
    const { data, response } = await client.GET("/me");

    expect(response.status).toBe(200);
    expect(data).toEqual(mockAuthUser);
    expect(refreshCalls).toBe(1);
    expect(meCalls).toBe(2); // original + one retry
  });

  it("does not retry when the refresh itself fails", async () => {
    let meCalls = 0;
    server.use(
      http.get("*/me", () => {
        meCalls += 1;
        return new HttpResponse(null, { status: 401 });
      }),
      http.post("*/auth/refresh", () => new HttpResponse(null, { status: 401 })),
    );

    const client = createSessionClient("http://localhost");
    const { response } = await client.GET("/me");

    expect(response.status).toBe(401);
    expect(meCalls).toBe(1); // no retry after a failed refresh
  });

  it("does not attempt a refresh for a 401 on an auth endpoint (no recursion)", async () => {
    let refreshCalls = 0;
    server.use(
      http.post("*/auth/refresh", () => {
        refreshCalls += 1;
        return new HttpResponse(null, { status: 401 });
      }),
    );

    const client = createSessionClient("http://localhost");
    const { response } = await client.POST("/auth/refresh");

    expect(response.status).toBe(401);
    expect(refreshCalls).toBe(1); // the call itself, never a re-refresh
  });
});
