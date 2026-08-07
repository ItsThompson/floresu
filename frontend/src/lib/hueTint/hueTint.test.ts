import { describe, expect, it } from "vitest";

import { hueTint } from "./hueTint";

describe("hueTint", () => {
  it("mixes the fill from the given hue at the requested strength", () => {
    expect(hueTint("var(--tag-3)", 18).backgroundColor).toBe(
      "color-mix(in oklab, var(--tag-3) 18%, var(--card))",
    );
  });

  it("mixes the ink from the same hue, deeper than the fill", () => {
    const tint = hueTint("var(--tag-3)", 18);

    expect(tint.color).toBe("color-mix(in oklab, var(--tag-3) 70%, var(--foreground))");
    expect(tint.color).not.toBe(tint.backgroundColor);
  });

  it("holds the ink strength fixed while the fill strength varies by surface", () => {
    const pill = hueTint("var(--tag-1)", 18);
    const avatar = hueTint("var(--tag-1)", 20);

    expect(pill.color).toBe(avatar.color);
    expect(pill.backgroundColor).not.toBe(avatar.backgroundColor);
  });
});
