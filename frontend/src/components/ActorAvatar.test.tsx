import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { colorForName } from "@/lib/colorForName";

import { ActorAvatar } from "./ActorAvatar";

describe("ActorAvatar", () => {
  it("renders the human as coral with a 'Y' initial and no bot glyph", () => {
    render(<ActorAvatar actorType="human" actorLabel={null} />);

    const avatar = screen.getByRole("img", { name: "You" });
    expect(avatar).toBeInTheDocument();
    expect(screen.getByText("Y")).toBeInTheDocument();
    // Coral comes from the accent token pair, not a computed hue.
    const swatch = avatar.querySelector("span")!;
    expect(swatch).toHaveClass("bg-accent", "text-accent-foreground");
    // The hairline ring keeps the disc visible where the surface shares its fill.
    expect(swatch).toHaveClass("ring-1", "ring-border");
    expect(swatch.getAttribute("style")).toBeNull();
    // Distinguished by shape too: the human carries no bot glyph.
    expect(screen.queryByTestId("agent-glyph")).not.toBeInTheDocument();
  });

  it("renders an agent with its hashed color, initial, and a bot glyph", () => {
    render(<ActorAvatar actorType="agent" actorLabel="claude" />);

    const avatar = screen.getByRole("img", { name: "claude" });
    expect(avatar).toBeInTheDocument();
    expect(screen.getByText("C")).toBeInTheDocument();
    // Shape differentiator present, and both shades come from the shared hash.
    expect(screen.getByTestId("agent-glyph")).toBeInTheDocument();
    const swatch = avatar.querySelector("span")!;
    const tagColor = colorForName("claude");

    expect(swatch.style.backgroundColor).toContain(tagColor);
    expect(swatch.style.color).toContain(tagColor);
    // A pastel fill cannot carry light text: the initial is a deeper mix.
    expect(swatch.style.color).not.toBe(swatch.style.backgroundColor);
  });

  it("falls back to 'Agent' when a named agent has no label", () => {
    render(<ActorAvatar actorType="agent" actorLabel={null} />);
    expect(screen.getByRole("img", { name: "Agent" })).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
  });
});
