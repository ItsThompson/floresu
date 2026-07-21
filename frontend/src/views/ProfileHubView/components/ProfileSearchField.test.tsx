import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ProfileSearchField } from "./ProfileSearchField";

describe("ProfileSearchField", () => {
  it("emits the trimmed query on submit", async () => {
    const onSearch = vi.fn();
    render(<ProfileSearchField onSearch={onSearch} />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Search experience"), "  payments  ");
    await user.keyboard("{Enter}");

    expect(onSearch).toHaveBeenCalledWith("payments");
  });

  it("does not emit an empty query", async () => {
    const onSearch = vi.fn();
    render(<ProfileSearchField onSearch={onSearch} />);
    const user = userEvent.setup();

    await user.click(screen.getByLabelText("Search experience"));
    await user.keyboard("{Enter}");

    expect(onSearch).not.toHaveBeenCalled();
  });
});
