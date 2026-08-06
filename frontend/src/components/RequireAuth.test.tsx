import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { mockAuthUser } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/renderWithProviders";
import { HERO_HEADLINE } from "@/views/LandingView/constants";

/** Make resume-on-mount authenticate, so guarded routes render the app shell. */
function authenticateOnResume() {
  server.use(http.post("*/auth/refresh", () => HttpResponse.json(mockAuthUser)));
}

describe("RequireAuth guard", () => {
  it("redirects an anonymous visitor from a protected route to sign-in", async () => {
    // Default MSW refresh returns 401 → the session resolves anonymous. The entry
    // is an in-app route: "/" is public, so it would prove nothing here.
    renderApp(["/home"]);
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
  });

  it("leaves the public page at / reachable without a session", async () => {
    renderApp(["/"]);
    expect(
      await screen.findByRole("heading", { level: 1, name: HERO_HEADLINE }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Welcome back" })).not.toBeInTheDocument();
  });

  it("renders the protected Home inside the app shell for an authenticated session", async () => {
    authenticateOnResume();
    renderApp(["/home"]);
    expect(await screen.findByRole("heading", { name: "Home" })).toBeInTheDocument();
    // The shell shows nav and the signed-in identity.
    expect(screen.getByRole("link", { name: "Home" })).toBeInTheDocument();
    expect(screen.getByText(mockAuthUser.email)).toBeInTheDocument();
  });

  it("signs out and returns to sign-in", async () => {
    authenticateOnResume();
    renderApp(["/home"]);
    await screen.findByRole("heading", { name: "Home" });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument(),
    );
  });
});
