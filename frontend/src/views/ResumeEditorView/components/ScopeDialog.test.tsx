import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ScopeDialog } from "./ScopeDialog";

const context = { bulletId: 100, newText: "Revised bullet text", usedInCount: 3 };

describe("ScopeDialog", () => {
  it("renders nothing when there is no pending prompt", () => {
    render(<ScopeDialog context={null} onApply={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows the shared count and marks Everywhere as higher-impact", () => {
    render(<ScopeDialog context={context} onApply={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole("dialog", { name: /used in 3 resumes/i })).toBeInTheDocument();
    expect(screen.getByText("Higher impact")).toBeInTheDocument();
  });

  it("defaults to 'Only this resume' and applies it", async () => {
    const onApply = vi.fn();
    render(<ScopeDialog context={context} onApply={onApply} onCancel={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(onApply).toHaveBeenCalledWith("this_resume");
  });

  it("applies 'everywhere' when the higher-impact option is chosen", async () => {
    const onApply = vi.fn();
    render(<ScopeDialog context={context} onApply={onApply} onCancel={vi.fn()} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("radio", { name: /Everywhere/i }));
    await user.click(screen.getByRole("button", { name: "Apply" }));
    expect(onApply).toHaveBeenCalledWith("everywhere");
  });

  it("cancels without applying", async () => {
    const onCancel = vi.fn();
    render(<ScopeDialog context={context} onApply={vi.fn()} onCancel={onCancel} />);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
