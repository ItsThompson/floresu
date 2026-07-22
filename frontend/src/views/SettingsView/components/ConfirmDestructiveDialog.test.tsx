import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDestructiveDialog } from "./ConfirmDestructiveDialog";

describe("ConfirmDestructiveDialog", () => {
  it("renders the title, description, and confirm label", () => {
    render(
      <ConfirmDestructiveDialog
        title="Delete this?"
        description="It cannot be undone."
        confirmLabel="Delete"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(screen.getByText("Delete this?")).toBeInTheDocument();
    expect(screen.getByText("It cannot be undone.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
  });

  it("confirms immediately when no explicit gate is required", async () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDestructiveDialog
        title="Revoke?"
        description="The agent loses access."
        confirmLabel="Revoke"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Revoke" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("keeps confirm disabled until the acknowledgement is checked", async () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDestructiveDialog
        title="Permanently delete?"
        description="Gone for good."
        confirmLabel="Delete permanently"
        acknowledgeLabel="I understand this cannot be undone."
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    const confirm = screen.getByRole("button", { name: "Delete permanently" });
    expect(confirm).toBeDisabled();

    await userEvent.click(screen.getByRole("checkbox"));
    expect(confirm).toBeEnabled();

    await userEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("keeps confirm disabled until the exact phrase is typed", async () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDestructiveDialog
        title="Delete your account?"
        description="Irreversible."
        confirmLabel="Delete account"
        typePhrase="me@floresu.com"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    const confirm = screen.getByRole("button", { name: "Delete account" });
    expect(confirm).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Confirmation phrase"), "me@floresu.wrong");
    expect(confirm).toBeDisabled();

    await userEvent.clear(screen.getByLabelText("Confirmation phrase"));
    await userEvent.type(screen.getByLabelText("Confirmation phrase"), "me@floresu.com");
    expect(confirm).toBeEnabled();
  });

  it("cancels via the Cancel button and the Escape key", async () => {
    const onCancel = vi.fn();
    render(
      <ConfirmDestructiveDialog
        title="Delete this?"
        description="It cannot be undone."
        confirmLabel="Delete"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);

    await userEvent.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it("disables both actions while the action is in flight", () => {
    render(
      <ConfirmDestructiveDialog
        title="Delete your account?"
        description="Irreversible."
        confirmLabel="Delete account"
        isBusy
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Delete account" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });
});
