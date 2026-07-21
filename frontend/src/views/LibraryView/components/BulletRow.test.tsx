import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { buildBullet } from "../__tests__/fixtures";
import { BulletRow } from "./BulletRow";

describe("BulletRow", () => {
  it("shows the shared marker and count for a bullet used by two or more resumes", () => {
    render(
      <BulletRow bullet={buildBullet({ used_in_count: 2 })} onEdit={vi.fn()} onArchive={vi.fn()} />,
    );
    expect(screen.getByText("Used in 2")).toBeInTheDocument();
    expect(screen.getByText("Shared")).toBeInTheDocument();
  });

  it("shows no shared marker for an unused bullet", () => {
    render(
      <BulletRow bullet={buildBullet({ used_in_count: 0 })} onEdit={vi.fn()} onArchive={vi.fn()} />,
    );
    expect(screen.getByText("Unused")).toBeInTheDocument();
    expect(screen.queryByText("Shared")).not.toBeInTheDocument();
  });

  it("reports edit and archive intents with the bullet", async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    const onArchive = vi.fn();
    const bullet = buildBullet({ id: 42 });

    render(<BulletRow bullet={bullet} onEdit={onEdit} onArchive={onArchive} />);

    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(onEdit).toHaveBeenCalledWith(bullet);

    await user.click(screen.getByRole("button", { name: "Archive" }));
    expect(onArchive).toHaveBeenCalledWith(42);
  });
});
