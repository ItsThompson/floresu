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
    // Distinguished by shape too: the human carries no bot glyph.
    expect(screen.queryByTestId("agent-glyph")).not.toBeInTheDocument();
  });

  it("renders an agent with its hashed color, initial, and a bot glyph", () => {
    render(<ActorAvatar actorType="agent" actorLabel="claude" />);

    const avatar = screen.getByRole("img", { name: "claude" });
    expect(avatar).toBeInTheDocument();
    expect(screen.getByText("C")).toBeInTheDocument();
    // Shape differentiator present, and the color is the shared hash (not coral).
    expect(screen.getByTestId("agent-glyph")).toBeInTheDocument();
    const swatch = avatar.querySelector("span");
    expect(swatch).toHaveStyle({ backgroundColor: colorForName("claude") });
  });

  it("falls back to 'Agent' when a named agent has no label", () => {
    render(<ActorAvatar actorType="agent" actorLabel={null} />);
    expect(screen.getByRole("img", { name: "Agent" })).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
  });
});
