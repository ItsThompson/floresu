import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { colorForName } from "@/lib/colorForName";

import { TagPill } from "./TagPill";

describe("TagPill", () => {
  it("colors the pill with the shared colorForName hash of its label", () => {
    const { container } = render(
      <>
        <TagPill label="backend" />
        <span data-testid="reference" style={{ color: colorForName("backend") }} />
      </>,
    );

    const pill = container.querySelector("span")!;
    const reference = container.querySelector('[data-testid="reference"]') as HTMLElement;
    // Both are set from colorForName("backend"); jsdom normalizes to the same rgb.
    expect(pill.style.color).toBe(reference.style.color);
    expect(pill.style.color).not.toBe("");
  });

  it("renders the label with its hash marker", () => {
    const { getByText } = render(<TagPill label="payments" />);
    expect(getByText("#payments")).toBeInTheDocument();
  });

  it("invokes onRemove when the remove control is clicked", async () => {
    const onRemove = vi.fn();
    const { getByRole } = render(<TagPill label="payments" onRemove={onRemove} />);
    await userEvent.click(getByRole("button", { name: "Remove tag payments" }));
    expect(onRemove).toHaveBeenCalledOnce();
  });
});
