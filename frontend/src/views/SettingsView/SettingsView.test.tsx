import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { buildAuthUser } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/renderWithProviders";

import { formatDate } from "./constants";

/**
 * Sociable tests for the Settings shell: the sub-navigation, the index redirect
 * to Account, and the Account section, driven through the real route tree.
 */

const USER = buildAuthUser({ email: "person@floresu.com", created_at: "2026-01-15T00:00:00Z" });

function authenticateOnResume() {
  server.use(http.post("*/auth/refresh", () => HttpResponse.json(USER)));
}

describe("SettingsView", () => {
  it("redirects the Settings index to the Account section", async () => {
    authenticateOnResume();

    renderApp(["/settings"]);

    expect(await screen.findByRole("heading", { name: "Account" })).toBeInTheDocument();
    const main = within(screen.getByRole("main"));
    expect(main.getByText(USER.email)).toBeInTheDocument();
    expect(main.getByText(formatDate(USER.created_at))).toBeInTheDocument();
  });

  it("navigates between sections through the sub-nav", async () => {
    authenticateOnResume();
    server.use(http.get("*/me/clients", () => HttpResponse.json([])));

    renderApp(["/settings/account"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("link", { name: "Connected agents" }));

    await waitFor(() => expect(screen.getByLabelText("MCP URL")).toBeInTheDocument());
  });
});
