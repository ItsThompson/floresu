import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { DEFAULT_MCP_URL } from "@/lib/mcpUrl";
import { buildAuthUser } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/renderWithProviders";

/** Resume-on-mount authenticates a user who has not finished onboarding yet. */
function startNotOnboarded() {
  server.use(
    http.post("*/auth/refresh", () =>
      HttpResponse.json(buildAuthUser({ has_completed_onboarding: false })),
    ),
  );
}

/** Resume-on-mount authenticates a user who has already finished onboarding. */
function startOnboarded() {
  server.use(
    http.post("*/auth/refresh", () =>
      HttpResponse.json(buildAuthUser({ has_completed_onboarding: true })),
    ),
  );
}

describe("OnboardingView route guard", () => {
  it("routes a non-onboarded user from the app to the wizard", async () => {
    startNotOnboarded();
    renderApp(["/home"]);
    expect(await screen.findByRole("heading", { name: "Welcome to Floresu" })).toBeInTheDocument();
  });

  it("routes an onboarded user away from the wizard to Home", async () => {
    startOnboarded();
    renderApp(["/onboarding"]);
    expect(await screen.findByRole("heading", { name: "Home" })).toBeInTheDocument();
  });
});

describe("OnboardingView wizard", () => {
  it("shows the first step with progress and no Back control", async () => {
    startNotOnboarded();
    renderApp(["/onboarding"]);

    expect(await screen.findByRole("heading", { name: "Welcome to Floresu" })).toBeInTheDocument();
    expect(screen.getByText("Step 1 of 4")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Skip" })).toBeInTheDocument();
  });

  it("walks the connect path Welcome → Choose → Connect → How it works → Home", async () => {
    startNotOnboarded();
    renderApp(["/onboarding"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Get started" }));
    expect(await screen.findByRole("heading", { name: "How do you want to start?" })).toBeInTheDocument();
    // Back appears once past the first step.
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    expect(screen.getByText(/Floresu parses nothing for you/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Connect your agent/ }));
    expect(await screen.findByRole("heading", { name: "Connect your agent" })).toBeInTheDocument();
    expect(screen.getByLabelText("MCP URL")).toHaveValue(DEFAULT_MCP_URL);
    expect(screen.getByText("Step 3 of 4")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "How Floresu works" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Finish" }));
    expect(await screen.findByRole("heading", { name: "Home" })).toBeInTheDocument();
  });

  it("goes back to the previous step", async () => {
    startNotOnboarded();
    renderApp(["/onboarding"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Get started" }));
    await screen.findByRole("heading", { name: "How do you want to start?" });
    await user.click(screen.getByRole("button", { name: "Back" }));

    expect(await screen.findByRole("heading", { name: "Welcome to Floresu" })).toBeInTheDocument();
  });

  it("completes onboarding and opens the worklog entry form when the manual path is chosen", async () => {
    startNotOnboarded();
    renderApp(["/onboarding"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Get started" }));
    await user.click(await screen.findByRole("button", { name: /Start manually/ }));

    // Lands on the worklog with the new-entry form already open. Reaching an
    // in-app route proves the flag flipped: otherwise the onboarding guard would
    // bounce it back to the wizard.
    expect(await screen.findByRole("form", { name: "Add entry" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Worklog" })).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "How do you want to start?" }),
    ).not.toBeInTheDocument();
  });

  it("keeps the user in the wizard with an inline error when the manual completion fails", async () => {
    startNotOnboarded();
    server.use(http.post("*/me/onboarding", () => new HttpResponse(null, { status: 500 })));
    renderApp(["/onboarding"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Get started" }));
    await user.click(await screen.findByRole("button", { name: /Start manually/ }));

    // The failure contract: the inline error shows and no navigation
    // happens, so the choice step stays put and the entry form never opens.
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How do you want to start?" })).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Add entry" })).not.toBeInTheDocument();
  });

  it("completes and lands on Home when skipped, leaving the wizard behind", async () => {
    startNotOnboarded();
    renderApp(["/onboarding"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Skip" }));

    // Landing on Home proves the flag flipped: otherwise the onboarding guard
    // would bounce "/home" straight back to the wizard. The app chrome is shown
    // and the wizard is gone.
    expect(await screen.findByRole("heading", { name: "Home" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Home" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Welcome to Floresu" })).not.toBeInTheDocument();
  });
});
