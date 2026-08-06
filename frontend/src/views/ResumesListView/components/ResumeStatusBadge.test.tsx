import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { buildResumeSummary } from "@/mocks/resumeFixtures";

import { ResumeStatusBadge } from "./ResumeStatusBadge";

describe("ResumeStatusBadge", () => {
  it("labels a living resume", () => {
    render(<ResumeStatusBadge resume={buildResumeSummary({ kind: "living" })} />);
    expect(screen.getByText("Living")).toBeInTheDocument();
  });

  it("labels a draft application resume", () => {
    render(
      <ResumeStatusBadge
        resume={buildResumeSummary({ kind: "application", status: "draft", job_application_id: 5 })}
      />,
    );
    expect(screen.getByText("Draft")).toBeInTheDocument();
  });

  it("labels a finalized resume with text and both the check and lock glyphs", () => {
    const { container } = render(
      <ResumeStatusBadge
        resume={buildResumeSummary({ kind: "application", status: "finalized" })}
      />,
    );
    expect(screen.getByText("Finalized")).toBeInTheDocument();
    // Done and frozen: two redundant glyphs, so the state never rests on the olive
    // tint alone.
    expect(container.querySelector(".lucide-check")).toBeInTheDocument();
    expect(container.querySelector(".lucide-lock")).toBeInTheDocument();
  });

  it("labels an archived resume, outranking its status", () => {
    render(
      <ResumeStatusBadge
        resume={buildResumeSummary({ status: "finalized", archived_at: "2026-07-21T00:00:00Z" })}
      />,
    );
    expect(screen.getByText("Archived")).toBeInTheDocument();
    expect(screen.queryByText("Finalized")).not.toBeInTheDocument();
  });
});
