import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { colorForName } from "@/lib/colorForName";

import { TagPill } from "./TagPill";

describe("TagPill", () => {
  it("mixes both the fill and the label ink from the label's hashed hue", () => {
    render(<TagPill label="backend" />);
    const pill = screen.getByText("#backend");
    const hue = colorForName("backend");

    expect(pill.style.backgroundColor).toContain(hue);
    expect(pill.style.color).toContain(hue);
    // A pastel fill cannot carry its own hue as ink: the label is a deeper mix.
    expect(pill.style.color).not.toBe(pill.style.backgroundColor);
  });

  it("renders the label with its hash marker", () => {
    render(<TagPill label="payments" />);
    expect(screen.getByText("#payments")).toBeInTheDocument();
  });

  it("carries the mono tag type and no border", () => {
    render(<TagPill label="backend" />);
    const pill = screen.getByText("#backend");

    expect(pill).toHaveClass("mono-tag", "rounded-full");
    // The tint is the pill's edge, so a border would double it.
    expect(pill.className.split(" ").some((name) => name.startsWith("border"))).toBe(false);
    expect(pill.style.borderColor).toBe("");
  });

  it("invokes onRemove when the remove control is clicked", async () => {
    const onRemove = vi.fn();
    render(<TagPill label="payments" onRemove={onRemove} />);

    await userEvent.click(screen.getByRole("button", { name: "Remove tag payments" }));
    expect(onRemove).toHaveBeenCalledOnce();
  });
});
