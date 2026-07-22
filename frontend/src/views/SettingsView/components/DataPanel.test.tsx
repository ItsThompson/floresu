import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { mockAuthUser } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/renderWithProviders";

/**
 * Sociable tests for the Data section: they drive the real route tree and account
 * state machine against the MSW-backed lifecycle routes. Only the network is
 * mocked.
 */

function authenticateOnResume() {
  server.use(http.post("*/auth/refresh", () => HttpResponse.json(mockAuthUser)));
}

describe("DataPanel", () => {
  it("offers data export as a credentialed download link", async () => {
    authenticateOnResume();

    renderApp(["/settings/data"]);

    const link = await screen.findByRole("link", { name: /export my data/i });
    expect(link).toHaveAttribute("href", expect.stringContaining("/account/export"));
    expect(link).toHaveAttribute("download");
  });

  it("deletes the account only after the email is typed, then returns to sign-in", async () => {
    authenticateOnResume();
    let deleteConfirm: string | null = null;
    server.use(
      http.delete("*/account", ({ request }) => {
        deleteConfirm = new URL(request.url).searchParams.get("confirm");
        return HttpResponse.json({ deleted: true, revoked_agent_count: 2 });
      }),
    );

    renderApp(["/settings/data"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /delete my account/i }));
    const confirm = screen.getByRole("button", { name: "Delete account" });
    // Irreversible and confirm-gated: disabled until the exact email is typed.
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText("Confirmation phrase"), mockAuthUser.email);
    expect(confirm).toBeEnabled();
    await user.click(confirm);

    // Account gone → session cleared → the session guard returns the user to sign-in.
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(deleteConfirm).toBe("true");
  });

  it("keeps the account when the delete confirmation is cancelled", async () => {
    authenticateOnResume();
    let deleteCalled = false;
    server.use(
      http.delete("*/account", () => {
        deleteCalled = true;
        return HttpResponse.json({ deleted: true, revoked_agent_count: 0 });
      }),
    );

    renderApp(["/settings/data"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /delete my account/i }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /delete my account/i })).toBeInTheDocument();
    expect(deleteCalled).toBe(false);
  });

  it("surfaces an error when account deletion fails", async () => {
    authenticateOnResume();
    server.use(http.delete("*/account", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));

    renderApp(["/settings/data"]);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /delete my account/i }));
    await user.type(screen.getByLabelText("Confirmation phrase"), mockAuthUser.email);
    await user.click(screen.getByRole("button", { name: "Delete account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn.t delete your account/i);
  });
});
