import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FilterCheckboxGroup } from "./FilterCheckboxGroup";

describe("FilterCheckboxGroup", () => {
  const options = [
    { value: 1, label: "Alpha" },
    { value: 2, label: "Beta" },
  ];

  it("renders nothing when there are no options", () => {
    const { container } = render(
      <FilterCheckboxGroup legend="Empty" options={[]} selected={[]} onToggle={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("reflects the selected values as checked", () => {
    render(
      <FilterCheckboxGroup legend="Kind" options={options} selected={[2]} onToggle={vi.fn()} />,
    );
    expect(screen.getByRole("checkbox", { name: "Alpha" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Beta" })).toBeChecked();
  });

  it("reports the toggled value", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(
      <FilterCheckboxGroup legend="Kind" options={options} selected={[]} onToggle={onToggle} />,
    );
    await user.click(screen.getByRole("checkbox", { name: "Alpha" }));
    expect(onToggle).toHaveBeenCalledWith(1);
  });
});
