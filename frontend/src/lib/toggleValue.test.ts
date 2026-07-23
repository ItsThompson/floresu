import { describe, expect, it } from "vitest";

import { toggleValue } from "./toggleValue";

describe("toggleValue", () => {
  it("adds a missing value and removes a present one", () => {
    expect(toggleValue([1, 2], 3)).toEqual([1, 2, 3]);
    expect(toggleValue([1, 2], 2)).toEqual([1]);
  });
});
