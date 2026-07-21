import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { buildResumeSummary } from "@/mocks/resumeFixtures";

import { NewResumeDialog } from "./NewResumeDialog";

const livingResumes = [
  buildResumeSummary({ id: 7, title: "Backend Engineer" }),
  buildResumeSummary({ id: 8, title: "Eng Manager" }),
];

describe("NewResumeDialog", () => {
  it("creates a blank living resume and reports the new id", async () => {
    const onCreate = vi.fn().mockResolvedValue(42);
    const onCreated = vi.fn();
    render(
      <NewResumeDialog isOpen onClose={vi.fn()} livingResumes={livingResumes} onCreate={onCreate} onCreated={onCreated} />,
    );
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Title"), "Staff Engineer");
    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(onCreate).toHaveBeenCalledWith({
      kind: "living",
      title: "Staff Engineer",
      source: { mode: "blank" },
    });
    expect(onCreated).toHaveBeenCalledWith(42);
  });

  it("seeds from an existing resume when a source is selected", async () => {
    const onCreate = vi.fn().mockResolvedValue(99);
    render(
      <NewResumeDialog isOpen onClose={vi.fn()} livingResumes={livingResumes} onCreate={onCreate} onCreated={vi.fn()} />,
    );
    const user = userEvent.setup();

    await user.click(screen.getByRole("radio", { name: /copy of an existing resume/i }));
    await user.selectOptions(screen.getByRole("combobox"), "8");
    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(onCreate).toHaveBeenCalledWith({
      kind: "living",
      title: null,
      source: { mode: "duplicate", duplicate_id: 8 },
    });
  });

  it("keeps the dialog open with an error when creation fails", async () => {
    const onCreate = vi.fn().mockResolvedValue(null);
    const onCreated = vi.fn();
    render(
      <NewResumeDialog isOpen onClose={vi.fn()} livingResumes={livingResumes} onCreate={onCreate} onCreated={onCreated} />,
    );
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Could not create/);
    expect(onCreated).not.toHaveBeenCalled();
  });
});
