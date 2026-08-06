import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "@/test/renderWithProviders";

import { Sidebar } from "./Sidebar";

const NAV_LABELS = [
  "Home",
  "Worklog",
  "Library",
  "Resumes",
  "Job Applications",
  "Profile",
  "Settings",
];

const ACTIVE_INDICATOR = "nav-active-indicator";

/** Render the sidebar with `/worklog` current, so exactly one item is active. */
function renderSidebarOnWorklog() {
  renderWithProviders(<Sidebar />, ["/worklog"]);
}

describe("Sidebar", () => {
  it("renders the lowercase serif wordmark", () => {
    renderSidebarOnWorklog();
    expect(screen.getByText("floresu")).toHaveClass("font-serif");
  });

  it("renders every nav entry as a link", () => {
    renderSidebarOnWorklog();
    for (const label of NAV_LABELS) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(screen.getAllByRole("link")).toHaveLength(NAV_LABELS.length);
    // Home is the one entry whose target is not its own lowercased label, and `/`
    // is the public page, so the destination is asserted rather than assumed.
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/home");
  });

  it("gives the current item the accent fill, the coral label, and the bloom indicator", () => {
    renderSidebarOnWorklog();
    const current = screen.getByRole("link", { name: "Worklog" });

    expect(current).toHaveClass("bg-accent", "text-accent-foreground");
    expect(within(current).getByTestId(ACTIVE_INDICATOR)).toHaveClass("bg-bloom");
  });

  it("leaves every other item quiet and without an indicator", () => {
    renderSidebarOnWorklog();
    const other = screen.getByRole("link", { name: "Library" });

    expect(other).toHaveClass("text-muted-foreground");
    expect(other).not.toHaveClass("bg-accent");
    expect(within(other).queryByTestId(ACTIVE_INDICATOR)).not.toBeInTheDocument();
    // The indicator marks the current route only, so there is exactly one.
    expect(screen.getAllByTestId(ACTIVE_INDICATOR)).toHaveLength(1);
  });

  it("renders sign-out as a button, because it is an action and not a destination", () => {
    renderSidebarOnWorklog();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Sign out" })).not.toBeInTheDocument();
  });
});
