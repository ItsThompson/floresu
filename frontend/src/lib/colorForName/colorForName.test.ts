import { describe, expect, it } from "vitest";

import { colorForName } from "./colorForName";

// The ten entries of the frozen palette, and nothing else.
const PALETTE_ENTRY = /^var\(--tag-([1-9]|10)\)$/;

describe("colorForName", () => {
  it("is deterministic: the same name always yields the same color", () => {
    expect(colorForName("claude")).toBe(colorForName("claude"));
    expect(colorForName("gpt-5")).toBe(colorForName("gpt-5"));
  });

  it("returns a palette token reference, never a color value", () => {
    expect(colorForName("claude")).toMatch(PALETTE_ENTRY);
  });

  it("stays inside the ten-entry palette for any name", () => {
    for (const name of ["a", "claude", "a much longer agent name", "z"]) {
      expect(colorForName(name)).toMatch(PALETTE_ENTRY);
    }
  });

  it("distinguishes different names by color", () => {
    // The palette has ten entries, so two names can legitimately share one. This pair is
    // chosen to land on different entries; changing either name needs that check re-done.
    expect(colorForName("claude")).not.toBe(colorForName("gpt-5"));
  });

  it("handles the empty string without throwing", () => {
    expect(colorForName("")).toBe("var(--tag-1)");
  });
});
