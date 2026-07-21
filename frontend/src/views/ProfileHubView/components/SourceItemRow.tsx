import { Archive, GripVertical } from "lucide-react";
import { Link } from "react-router";

import { formatDateRange } from "@/lib/formatDate";
import type { DragHandleProps } from "@/lib/reorder";

import type { SourceSummary } from "../types";

interface SourceItemRowProps {
  source: SourceSummary;
  handleProps: DragHandleProps;
  isDragging: boolean;
  onArchive: (id: number) => void;
}

/**
 * One source row inside a section card: a grab handle, a link into the source's
 * three-column detail, its date range, and an archive control. The whole row is
 * both a drag source and a drop target (a flat list), so items reorder within the
 * card by dragging one onto another.
 */
export function SourceItemRow({ source, handleProps, isDragging, onArchive }: SourceItemRowProps) {
  const range = formatDateRange(source.date_start, source.date_end);
  return (
    <li
      {...handleProps}
      className={`group border-border flex items-center gap-2 rounded-md border px-2 py-1.5 ${
        isDragging ? "opacity-50" : ""
      }`}
    >
      <GripVertical
        aria-hidden
        className="text-muted-foreground size-3.5 shrink-0 cursor-grab"
      />
      <Link
        to={`/profile/sources/${source.id}`}
        className="flex min-w-0 flex-1 flex-col hover:underline"
      >
        <span className="truncate text-sm font-medium">{source.display_label}</span>
        {range && <span className="text-muted-foreground text-xs">{range}</span>}
      </Link>
      <button
        type="button"
        aria-label={`Archive ${source.display_label}`}
        onClick={() => onArchive(source.id)}
        className="text-muted-foreground hover:text-destructive rounded p-1 opacity-0 outline-none group-hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-[3px] focus-visible:ring-ring/50"
      >
        <Archive className="size-3.5" />
      </button>
    </li>
  );
}
