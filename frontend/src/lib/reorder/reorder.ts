import { useCallback, useRef, useState } from "react";

/**
 * Drag-to-reorder for a single list, shared across views (profile section cards,
 * source items, skills). The reference stack ships no drag library, so this is a
 * thin wrapper over the native HTML5 drag events.
 *
 * It holds no order state of its own: the displayed order comes from the caller's
 * `ids`, and a drop computes the next order and hands it back through `onReorder`.
 * The caller persists it (localStorage, a `/reorder` POST) and updates its own
 * data, which flows back in as new `ids`. The dragged id is tracked internally
 * rather than through `event.dataTransfer`, so the handlers run identically under
 * jsdom (where `dataTransfer` is absent) and in the browser.
 */

export type ReorderId = string | number;

/** Move the item at `fromIndex` so it sits at `toIndex`, returning a new array. */
export function moveItem<T>(items: readonly T[], fromIndex: number, toIndex: number): T[] {
  const next = items.slice();
  const [moved] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moved);
  return next;
}

/** Reorder `ids` by moving `fromId` to the position currently held by `toId`. */
export function reorderIds(ids: readonly ReorderId[], fromId: ReorderId, toId: ReorderId): ReorderId[] {
  const fromIndex = ids.indexOf(fromId);
  const toIndex = ids.indexOf(toId);
  if (fromIndex === -1 || toIndex === -1 || fromIndex === toIndex) return ids.slice();
  return moveItem(ids, fromIndex, toIndex);
}

/**
 * Rebuild `items` in `orderedIds` order, reassigning each `sort_order` to its new
 * index. Ids absent from `items` are dropped; the input is not mutated. This is the
 * downstream partner of `reorderIds`: a drag produces the new id order, then this
 * writes the positional `sort_order` the backend persists.
 */
export function reorderBySortOrder<T extends { id: number; sort_order: number }>(
  items: readonly T[],
  orderedIds: number[],
): T[] {
  const byId = new Map(items.map((item) => [item.id, item]));
  return orderedIds.flatMap((id, index) => {
    const item = byId.get(id);
    return item ? [{ ...item, sort_order: index }] : [];
  });
}

export interface DragSourceProps {
  draggable: true;
  onDragStart: () => void;
  onDragEnd: () => void;
  "aria-grabbed": boolean;
}

export interface DragTargetProps {
  onDragOver: (event: { preventDefault: () => void }) => void;
  onDrop: (event: { preventDefault: () => void }) => void;
}

export type DragHandleProps = DragSourceProps & DragTargetProps;

export interface DragReorder {
  /** The id currently being dragged, or null; drives the drag affordance. */
  draggingId: ReorderId | null;
  /** Drag-source props: spread onto the grabbable element (e.g. a handle). */
  sourceProps: (id: ReorderId) => DragSourceProps;
  /** Drop-target props: spread onto the element that accepts a drop. */
  targetProps: (id: ReorderId) => DragTargetProps;
  /** Source + target on one element, for the common flat-list case. */
  handleProps: (id: ReorderId) => DragHandleProps;
}

/**
 * Nested reorder contexts (reorderable cards that themselves contain reorderable
 * rows) need the drag source and drop target on different elements to avoid one
 * drop firing both handlers. `sourceProps`/`targetProps` split them; `handleProps`
 * combines them for a flat list where one element is both.
 */
export function useDragReorder(
  ids: readonly ReorderId[],
  onReorder: (nextIds: ReorderId[]) => void,
): DragReorder {
  const draggingRef = useRef<ReorderId | null>(null);
  const [draggingId, setDraggingId] = useState<ReorderId | null>(null);

  const clear = useCallback(() => {
    draggingRef.current = null;
    setDraggingId(null);
  }, []);

  const sourceProps = useCallback(
    (id: ReorderId): DragSourceProps => ({
      draggable: true,
      "aria-grabbed": draggingId === id,
      onDragStart: () => {
        draggingRef.current = id;
        setDraggingId(id);
      },
      onDragEnd: clear,
    }),
    [draggingId, clear],
  );

  const targetProps = useCallback(
    (id: ReorderId): DragTargetProps => ({
      onDragOver: (event) => {
        // Only a preventDefault-ed dragover marks a valid drop target.
        if (draggingRef.current !== null) event.preventDefault();
      },
      onDrop: (event) => {
        event.preventDefault();
        const from = draggingRef.current;
        if (from !== null && from !== id) onReorder(reorderIds(ids, from, id));
        clear();
      },
    }),
    [ids, onReorder, clear],
  );

  const handleProps = useCallback(
    (id: ReorderId): DragHandleProps => ({ ...sourceProps(id), ...targetProps(id) }),
    [sourceProps, targetProps],
  );

  return { draggingId, sourceProps, targetProps, handleProps };
}
