import { describe, expect, it } from "vitest";

import { colorForName } from "./colorForName";

describe("colorForName", () => {
  it("is deterministic: the same name always yields the same color", () => {
    expect(colorForName("claude")).toBe(colorForName("claude"));
    expect(colorForName("gpt-5")).toBe(colorForName("gpt-5"));
  });

  it("produces a legible hsl color with the fixed saturation and lightness", () => {
    expect(colorForName("claude")).toMatch(/^hsl\(\d{1,3} 65% 45%\)$/);
  });

  it("keeps the hue within a valid range", () => {
    for (const name of ["a", "claude", "a much longer agent name", "z"]) {
      const hue = Number(colorForName(name).match(/^hsl\((\d{1,3}) /)?.[1]);
      expect(hue).toBeGreaterThanOrEqual(0);
      expect(hue).toBeLessThan(360);
    }
  });

  it("distinguishes different names by color", () => {
    expect(colorForName("claude")).not.toBe(colorForName("gpt-5"));
  });

  it("handles the empty string without throwing", () => {
    expect(colorForName("")).toMatch(/^hsl\(0 65% 45%\)$/);
  });
});
