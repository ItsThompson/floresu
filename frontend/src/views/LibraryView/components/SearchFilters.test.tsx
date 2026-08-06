import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DEFAULT_SEARCH_FILTERS } from "@/lib/searchFilters";

import { buildSource, buildTag } from "../test-support/fixtures";
import { SearchFilters } from "./SearchFilters";

function renderFilters(onChange = vi.fn()) {
  render(
    <SearchFilters
      sources={[buildSource({ id: 1, display_label: "Acme" })]}
      tags={[buildTag({ id: 1, label: "backend" })]}
      filters={DEFAULT_SEARCH_FILTERS}
      onChange={onChange}
    />,
  );
  return onChange;
}

describe("SearchFilters", () => {
  it("reports a source-kind toggle", async () => {
    const user = userEvent.setup();
    const onChange = renderFilters();
    await user.click(screen.getByRole("checkbox", { name: "Role" }));
    expect(onChange).toHaveBeenCalledWith({ kinds: ["role"] });
  });

  it("reports a source toggle by id", async () => {
    const user = userEvent.setup();
    const onChange = renderFilters();
    await user.click(screen.getByRole("checkbox", { name: "Acme" }));
    expect(onChange).toHaveBeenCalledWith({ sourceIds: [1] });
  });

  it("reports a tag toggle by label", async () => {
    const user = userEvent.setup();
    const onChange = renderFilters();
    await user.click(screen.getByRole("checkbox", { name: "backend" }));
    expect(onChange).toHaveBeenCalledWith({ tags: ["backend"] });
  });

  it("reports a layer change", async () => {
    const user = userEvent.setup();
    const onChange = renderFilters();
    await user.selectOptions(screen.getByLabelText("Layer"), "library");
    expect(onChange).toHaveBeenCalledWith({ layer: "library" });
  });

  it("reports a date-range change", () => {
    const onChange = renderFilters();
    fireEvent.change(screen.getByLabelText("From date"), { target: { value: "2026-01-01" } });
    expect(onChange).toHaveBeenCalledWith({ dateFrom: "2026-01-01" });
  });
});
