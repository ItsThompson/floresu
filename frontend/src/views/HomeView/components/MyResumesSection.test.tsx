import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { buildResumeSummary } from "@/mocks/resumeFixtures";
import { renderWithProviders } from "@/test/renderWithProviders";

import type { HomeSection, ResumeSummary } from "../types";
import { MyResumesSection } from "./MyResumesSection";

function renderSection(section: HomeSection<ResumeSummary>) {
  return renderWithProviders(<MyResumesSection section={section} />);
}

describe("MyResumesSection", () => {
  it("is an individually named region", () => {
    renderSection({ items: [], status: "loading" });
    expect(screen.getByRole("region", { name: "My resumes" })).toBeInTheDocument();
  });

  it("shows a loading message while the section loads", () => {
    renderSection({ items: [], status: "loading" });
    expect(screen.getByText("Loading resumes…")).toBeInTheDocument();
  });

  it("shows an inline error when the read fails", () => {
    renderSection({ items: [], status: "error" });
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load your resumes.");
  });

  it("shows its own empty state when there are no resumes", () => {
    renderSection({ items: [], status: "ready" });
    expect(screen.getByText("No resumes yet.")).toBeInTheDocument();
  });

  it("keeps the empty state calm: one primary action and no serif line", () => {
    renderSection({ items: [], status: "ready" });

    expect(screen.getByRole("link", { name: "Start a resume" })).toHaveAttribute(
      "href",
      "/resumes",
    );
    // Home's single display moment belongs to the worklog region, not this one.
    expect(document.querySelectorAll('[class*="display-"]')).toHaveLength(0);
  });

  it("lists each resume with a link that opens its editor", () => {
    renderSection({
      items: [
        buildResumeSummary({ id: 10, title: "Backend Engineer" }),
        buildResumeSummary({ id: 12, title: "Globex Staff Engineer" }),
      ],
      status: "ready",
    });

    expect(screen.getByText("Backend Engineer")).toBeInTheDocument();
    expect(screen.getByText("Globex Staff Engineer")).toBeInTheDocument();

    const links = screen.getAllByRole("link", { name: "Open" });
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/resumes/10", "/resumes/12"]);
  });
});
