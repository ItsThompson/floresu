import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useDragList } from "./useDragList";

function dragEvent() {
  return { preventDefault: vi.fn() } as unknown as React.DragEvent;
}

describe("useDragList", () => {
  it("reorders by moving the dragged index onto the drop index", () => {
    const onReorder = vi.fn();
    const { result } = renderHook(() => useDragList(["a", "b", "c"], onReorder));

    act(() => result.current.handlers(0).onDragStart());
    act(() => result.current.handlers(2).onDrop());

    expect(onReorder).toHaveBeenCalledWith(["b", "c", "a"]);
  });

  it("does not reorder when dropping onto the same index", () => {
    const onReorder = vi.fn();
    const { result } = renderHook(() => useDragList(["a", "b"], onReorder));

    act(() => result.current.handlers(1).onDragStart());
    act(() => result.current.handlers(1).onDrop());

    expect(onReorder).not.toHaveBeenCalled();
  });

  it("tracks the dragging index and clears it on drag end", () => {
    const { result } = renderHook(() => useDragList(["a", "b"], vi.fn()));

    act(() => result.current.handlers(1).onDragStart());
    expect(result.current.dragIndex).toBe(1);

    act(() => result.current.handlers(1).onDragEnd());
    expect(result.current.dragIndex).toBeNull();
  });

  it("prevents default on drag over so the element is a valid drop target", () => {
    const { result } = renderHook(() => useDragList(["a"], vi.fn()));
    const event = dragEvent();
    act(() => result.current.handlers(0).onDragOver(event));
    expect(event.preventDefault).toHaveBeenCalled();
  });
});
