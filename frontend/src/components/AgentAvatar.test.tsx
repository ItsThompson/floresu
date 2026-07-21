import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { colorForName } from "@/lib/colorForName";

import { AgentAvatar } from "./AgentAvatar";

describe("AgentAvatar", () => {
  it("renders the name's initial and a bot glyph", () => {
    render(<AgentAvatar name="Claude" />);
    const avatar = screen.getByRole("img", { name: "Claude" });
    expect(avatar).toBeInTheDocument();
    expect(screen.getByText("C")).toBeInTheDocument();
    expect(screen.getByTestId("agent-glyph")).toBeInTheDocument();
  });

  it("colors the swatch by the shared hash of the name", () => {
    render(<AgentAvatar name="Cursor" />);
    const swatch = screen.getByRole("img", { name: "Cursor" }).querySelector("span");
    expect(swatch).toHaveStyle({ backgroundColor: colorForName("Cursor") });
  });
});
