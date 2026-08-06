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

  it("mixes both the fill and the initial from the name's hashed hue", () => {
    render(<AgentAvatar name="Cursor" />);
    const swatch = screen.getByRole("img", { name: "Cursor" }).querySelector("span")!;
    const tagColor = colorForName("Cursor");

    expect(swatch.style.backgroundColor).toContain(tagColor);
    expect(swatch.style.color).toContain(tagColor);
    // A pastel fill cannot carry light text: the initial is a deeper mix.
    expect(swatch.style.color).not.toBe(swatch.style.backgroundColor);
  });
});
