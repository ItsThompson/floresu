import { useState, type DragEvent } from "react";

import { moveInOrder } from "../documentOps";

interface DragHandlers {
  draggable: true;
  onDragStart: () => void;
  onDragOver: (event: DragEvent) => void;
  onDrop: () => void;
  onDragEnd: () => void;
}

export interface DragList {
  /** The index currently being dragged, for a drop-target highlight. */
  dragIndex: number | null;
  /** Native drag handlers to spread onto the draggable element at `index`. */
  handlers: (index: number) => DragHandlers;
}

/**
 * Native drag-to-reorder for an ordered id list. On drop it computes the new
 * order with a pure move and hands it to `onReorder` (which persists it), so the
 * reorder never addresses an item by anything but its position in the list. Used
 * for both sections and the items within a section.
 */
export function useDragList(ids: string[], onReorder: (nextIds: string[]) => void): DragList {
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  const handlers = (index: number): DragHandlers => ({
    draggable: true,
    onDragStart: () => setDragIndex(index),
    onDragOver: (event) => event.preventDefault(),
    onDrop: () => {
      if (dragIndex !== null && dragIndex !== index) {
        onReorder(moveInOrder(ids, dragIndex, index));
      }
      setDragIndex(null);
    },
    onDragEnd: () => setDragIndex(null),
  });

  return { dragIndex, handlers };
}
