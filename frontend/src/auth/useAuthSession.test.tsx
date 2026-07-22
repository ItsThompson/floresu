import { renderHook, waitFor } from "@testing-library/react";
import { act } from "react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { createApiClient } from "@/api";
import { server } from "@/mocks/server";
import { buildAuthUser, mockAuthUser } from "@/mocks/data";

import { useAuthSession } from "./useAuthSession";

function renderSession() {
  // A credential-free client is enough here; MSW intercepts by URL. An absolute
  // base lets undici parse the request URL under jsdom. Create it once so the
  // hook callbacks stay stable (a new client each render would re-run resume).
  const client = createApiClient("http://localhost");
  return renderHook(() => useAuthSession(client));
}

describe("useAuthSession", () => {
  it("resolves to anonymous on mount when refresh finds no session", async () => {
    const { result } = renderSession();
    await waitFor(() => expect(result.current.status).toBe("anonymous"));
    expect(result.current.user).toBeNull();
  });

  it("resumes an existing session on mount when refresh returns a user", async () => {
    server.use(http.post("*/auth/refresh", () => HttpResponse.json(mockAuthUser)));
    const { result } = renderSession();
    await waitFor(() => expect(result.current.status).toBe("authenticated"));
    expect(result.current.user).toEqual(mockAuthUser);
  });

  it("authenticates on login and exposes the returned user", async () => {
    const { result } = renderSession();
    await waitFor(() => expect(result.current.status).toBe("anonymous"));

    let outcome;
    await act(async () => {
      outcome = await result.current.login({ email: "demo@floresu.app", password: "Str0ngPass" });
    });
    expect(outcome).toEqual({ ok: true });
    expect(result.current.status).toBe("authenticated");
    expect(result.current.user).toEqual(mockAuthUser);
  });

  it("returns a field error result on a failed register without authenticating", async () => {
    server.use(
      http.post("*/auth/register", () =>
        HttpResponse.json(
          { detail: "An account with this email already exists.", fields: { email: "Taken." } },
          { status: 409 },
        ),
      ),
    );
    const { result } = renderSession();
    await waitFor(() => expect(result.current.status).toBe("anonymous"));

    let outcome;
    await act(async () => {
      outcome = await result.current.register({ email: "demo@floresu.app", password: "Str0ngPass" });
    });
    expect(outcome).toEqual({
      ok: false,
      message: "An account with this email already exists.",
      fields: { email: "Taken." },
    });
    expect(result.current.status).toBe("anonymous");
  });

  it("clears the session on logout", async () => {
    server.use(http.post("*/auth/refresh", () => HttpResponse.json(mockAuthUser)));
    const { result } = renderSession();
    await waitFor(() => expect(result.current.status).toBe("authenticated"));

    await act(async () => {
      await result.current.logout();
    });
    expect(result.current.status).toBe("anonymous");
    expect(result.current.user).toBeNull();
  });

  it("adopts the onboarded user from the server when completing onboarding", async () => {
    server.use(
      http.post("*/auth/refresh", () =>
        HttpResponse.json(buildAuthUser({ has_completed_onboarding: false })),
      ),
      http.post("*/me/onboarding", () =>
        HttpResponse.json(buildAuthUser({ has_completed_onboarding: true })),
      ),
    );
    const { result } = renderSession();
    await waitFor(() => expect(result.current.status).toBe("authenticated"));
    expect(result.current.user?.has_completed_onboarding).toBe(false);

    let outcome;
    await act(async () => {
      outcome = await result.current.completeOnboarding();
    });

    expect(outcome).toEqual({ ok: true });
    expect(result.current.user?.has_completed_onboarding).toBe(true);
    expect(result.current.status).toBe("authenticated");
  });
});
