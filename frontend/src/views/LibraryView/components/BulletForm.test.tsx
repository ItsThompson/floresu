import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { buildSource, buildWorklogEntry } from "../test-support/fixtures";
import type { BulletFormValues } from "../types";
import { BulletForm } from "./BulletForm";

const emptyValues: BulletFormValues = { text: "", sourceIds: [], worklogIds: [] };

function renderForm(overrides: Partial<Parameters<typeof BulletForm>[0]> = {}) {
  const props = {
    mode: "create" as const,
    initialValues: emptyValues,
    sources: [buildSource({ id: 1, display_label: "Acme" })],
    worklogEntries: [
      buildWorklogEntry({ id: 30, title: "Shipped payments", entry_date: "2026-07-18" }),
    ],
    isSaving: false,
    error: null as string | null,
    onSubmit: vi.fn(),
    onCancel: vi.fn(),
    ...overrides,
  };
  render(<BulletForm {...props} />);
  return props;
}

describe("BulletForm", () => {
  it("blocks submit until the statement has text", async () => {
    const user = userEvent.setup();
    const props = renderForm();

    expect(screen.getByRole("button", { name: "Save bullet" })).toBeDisabled();
    await user.type(screen.getByLabelText("Statement"), "A framing");
    expect(screen.getByRole("button", { name: "Save bullet" })).toBeEnabled();
    expect(props.onSubmit).not.toHaveBeenCalled();
  });

  it("submits the trimmed statement with selected source and worklog links", async () => {
    const user = userEvent.setup();
    const props = renderForm();

    await user.type(screen.getByLabelText("Statement"), "  Cut latency  ");
    await user.click(screen.getByRole("checkbox", { name: "Acme" }));
    await user.click(screen.getByRole("checkbox", { name: "Shipped payments (2026-07-18)" }));
    await user.click(screen.getByRole("button", { name: "Save bullet" }));

    expect(props.onSubmit).toHaveBeenCalledWith({
      text: "Cut latency",
      sourceIds: [1],
      worklogIds: [30],
    });
  });

  it("seeds edit mode from the initial values", () => {
    renderForm({
      mode: "edit",
      initialValues: { text: "Existing", sourceIds: [1], worklogIds: [] },
    });
    expect(screen.getByRole("form", { name: "Edit bullet" })).toBeInTheDocument();
    expect(screen.getByLabelText("Statement")).toHaveValue("Existing");
    expect(screen.getByRole("checkbox", { name: "Acme" })).toBeChecked();
  });

  it("renders an inline write error and keeps the form usable", () => {
    renderForm({ error: "Statement is too long" });
    expect(screen.getByRole("alert")).toHaveTextContent("Statement is too long");
  });

  it("reports cancel intent", async () => {
    const user = userEvent.setup();
    const props = renderForm();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(props.onCancel).toHaveBeenCalled();
  });
});
