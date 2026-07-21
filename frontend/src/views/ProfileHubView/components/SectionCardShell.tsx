import { GripVertical } from "lucide-react";
import type { ReactNode } from "react";

import type { DragSourceProps, DragTargetProps } from "@/lib/reorder";

interface SectionCardShellProps {
  title: string;
  /** Drag-source props for the reorder handle (the card is grabbed by its handle). */
  sourceProps: DragSourceProps;
  /** Drop-target props for the whole card, so a card can be dropped anywhere on it. */
  targetProps: DragTargetProps;
  isDragging: boolean;
  /** Trailing header control (an "open section" link or an add control). */
  headerAction?: ReactNode;
  children: ReactNode;
}

/**
 * Presentational chrome for one profile-hub section card: a grab handle, a title,
 * an optional header action, and the card body. The card is a drop target
 * anywhere on its surface; only the handle is a drag source, so grabbing a card
 * never conflicts with dragging the reorderable rows inside its body.
 */
export function SectionCardShell({
  title,
  sourceProps,
  targetProps,
  isDragging,
  headerAction,
  children,
}: SectionCardShellProps) {
  return (
    <article
      aria-label={title}
      {...targetProps}
      className={`border-border bg-card flex flex-col gap-3 rounded-xl border p-4 transition-opacity ${
        isDragging ? "opacity-50" : ""
      }`}
    >
      <header className="flex items-center gap-2">
        <button
          type="button"
          aria-label={`Drag to reorder ${title}`}
          className="text-muted-foreground hover:text-foreground cursor-grab rounded p-0.5 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          {...sourceProps}
        >
          <GripVertical className="size-4" />
        </button>
        <h2 className="flex-1 text-sm font-semibold tracking-tight">{title}</h2>
        {headerAction}
      </header>
      {children}
    </article>
  );
}
