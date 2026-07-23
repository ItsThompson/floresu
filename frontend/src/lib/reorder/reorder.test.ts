import { describe, expect, it } from "vitest";

import { moveItem, reorderBySortOrder, reorderIds } from "./reorder";

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

describe("reorderBySortOrder", () => {
  it("reassigns sort_order to the positional index of the new order", () => {
    const items = [
      { id: 10, sort_order: 0, name: "a" },
      { id: 20, sort_order: 1, name: "b" },
      { id: 30, sort_order: 2, name: "c" },
    ];
    expect(reorderBySortOrder(items, [30, 10, 20])).toEqual([
      { id: 30, sort_order: 0, name: "c" },
      { id: 10, sort_order: 1, name: "a" },
      { id: 20, sort_order: 2, name: "b" },
    ]);
  });

  it("drops ids absent from items, keeping each surviving id's index in orderedIds", () => {
    const items = [
      { id: 1, sort_order: 0 },
      { id: 2, sort_order: 1 },
    ];
    expect(reorderBySortOrder(items, [2, 99, 1])).toEqual([
      { id: 2, sort_order: 0 },
      { id: 1, sort_order: 2 },
    ]);
  });

  it("does not mutate the input items", () => {
    const items = [
      { id: 1, sort_order: 0 },
      { id: 2, sort_order: 1 },
    ];
    reorderBySortOrder(items, [2, 1]);
    expect(items).toEqual([
      { id: 1, sort_order: 0 },
      { id: 2, sort_order: 1 },
    ]);
  });

  it("yields an empty array when orderedIds is empty", () => {
    const items = [{ id: 1, sort_order: 0 }];
    expect(reorderBySortOrder(items, [])).toEqual([]);
  });
});
