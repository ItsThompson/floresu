import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { buildEntry } from "@/mocks/worklogFixtures";
import { renderWithProviders } from "@/test/renderWithProviders";

import type { HomeSection, WorklogSummary } from "../types";
import { RecentWorklogSection } from "./RecentWorklogSection";

function renderSection(section: HomeSection<WorklogSummary>) {
  return renderWithProviders(<RecentWorklogSection section={section} />);
}

describe("RecentWorklogSection", () => {
  it("is an individually named region", () => {
    renderSection({ items: [], status: "loading" });
    expect(screen.getByRole("region", { name: "Recent worklog" })).toBeInTheDocument();
  });

  it("shows a loading message while the section loads", () => {
    renderSection({ items: [], status: "loading" });
    expect(screen.getByText("Loading worklog…")).toBeInTheDocument();
  });

  it("shows an inline error when the read fails", () => {
    renderSection({ items: [], status: "error" });
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load your recent worklog.");
  });

  it("shows its own empty state when there are no entries", () => {
    renderSection({ items: [], status: "ready" });
    expect(screen.getByText("No worklog entries yet.")).toBeInTheDocument();
  });

  it("gives the empty state Home's one serif line and a single primary action", () => {
    renderSection({ items: [], status: "ready" });

    expect(screen.getByText("Start with what you did today.")).toHaveClass("display-m");
    expect(document.querySelectorAll('[class*="display-"]')).toHaveLength(1);
    // The action opens the entry form on arrival rather than the bare timeline.
    expect(screen.getByRole("link", { name: "Log an entry" })).toHaveAttribute(
      "href",
      "/worklog?new=1",
    );
  });

  it("lists entries with their title and date", () => {
    renderSection({
      items: [
        buildEntry({ id: 2, title: "Shipped payments migration", entry_date: "2026-07-18" }),
        buildEntry({ id: 1, title: "Wrote the design doc", entry_date: "2026-06-02" }),
      ],
      status: "ready",
    });

    expect(screen.getByText("Shipped payments migration")).toBeInTheDocument();
    expect(screen.getByText("Jul 18, 2026")).toHaveClass("mono-meta");
    expect(screen.getByText("Wrote the design doc")).toBeInTheDocument();
    expect(screen.getByText("Jun 2, 2026")).toBeInTheDocument();
    // A preview card stays calm: no display line once it has entries to show.
    expect(document.querySelectorAll('[class*="display-"]')).toHaveLength(0);
  });
});
