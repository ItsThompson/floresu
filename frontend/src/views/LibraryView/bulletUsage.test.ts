import { describe, expect, it } from "vitest";

import { isShared, usedInLabel } from "./bulletUsage";

describe("usedInLabel / isShared", () => {
  it("labels an unused bullet and shows no shared marker", () => {
    expect(usedInLabel(0)).toBe("Unused");
    expect(isShared(0)).toBe(false);
  });

  it("labels a single use without the shared marker", () => {
    expect(usedInLabel(1)).toBe("Used in 1");
    expect(isShared(1)).toBe(false);
  });

  it("marks a bullet shared once two or more resumes use it", () => {
    expect(usedInLabel(2)).toBe("Used in 2");
    expect(isShared(2)).toBe(true);
  });
});
