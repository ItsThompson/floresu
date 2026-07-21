import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResumeStatusBadge } from "./ResumeStatusBadge";

describe("ResumeStatusBadge", () => {
  it("labels a draft resume", () => {
    render(<ResumeStatusBadge status="draft" />);
    expect(screen.getByText("Draft")).toBeInTheDocument();
  });

  it("labels a finalized resume with text (meaning not by color alone)", () => {
    render(<ResumeStatusBadge status="finalized" />);
    expect(screen.getByText("Finalized")).toBeInTheDocument();
  });
});
