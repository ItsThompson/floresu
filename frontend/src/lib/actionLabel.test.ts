import { describe, expect, it } from "vitest";

import { actionLabel } from "./actionLabel";

describe("actionLabel", () => {
  it.each([
    ["create", "created"],
    ["update", "updated"],
    ["archive", "archived"],
    ["restore", "restored"],
    ["delete", "deleted"],
    ["finalize", "finalized"],
    ["promote", "promoted"],
    ["reorder", "reordered"],
    ["render", "rendered"],
    ["tag", "tagged"],
  ])("maps the %s action to its past-tense label %s", (action, expected) => {
    expect(actionLabel(action)).toBe(expected);
  });

  it("falls back to the raw verb for an unknown action", () => {
    expect(actionLabel("teleport")).toBe("teleport");
  });
});
