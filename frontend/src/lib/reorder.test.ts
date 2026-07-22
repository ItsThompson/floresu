import { describe, expect, it } from "vitest";

import { moveItem, reorderIds } from "./reorder";

describe("moveItem", () => {
  it("moves an item forward to a later index", () => {
    expect(moveItem([1, 2, 3, 4], 0, 2)).toEqual([2, 3, 1, 4]);
  });

  it("moves an item backward to an earlier index", () => {
    expect(moveItem([1, 2, 3, 4], 3, 1)).toEqual([1, 4, 2, 3]);
  });

  it("does not mutate the input array", () => {
    const input = [1, 2, 3];
    moveItem(input, 0, 2);
    expect(input).toEqual([1, 2, 3]);
  });
});

describe("reorderIds", () => {
  it("moves the dragged id to the target id's position", () => {
    expect(reorderIds(["a", "b", "c"], "a", "c")).toEqual(["b", "c", "a"]);
  });

  it("returns an unchanged copy when dragging onto itself", () => {
    expect(reorderIds(["a", "b", "c"], "b", "b")).toEqual(["a", "b", "c"]);
  });

  it("returns an unchanged copy when an id is not present", () => {
    expect(reorderIds([1, 2, 3], 9, 2)).toEqual([1, 2, 3]);
  });
});
