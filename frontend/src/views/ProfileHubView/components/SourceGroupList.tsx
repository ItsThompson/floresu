import { Plus } from "lucide-react";
import { Link } from "react-router";

import { useDragReorder } from "@/lib/reorder";

import { SECTION_PREVIEW_LIMIT } from "../constants";
import type { SourceKind, SourceSummary } from "../types";
import { SourceItemRow } from "./SourceItemRow";

interface SourceGroupListProps {
  kind: SourceKind;
  /** A sub-heading when a card holds more than one kind (e.g. education + certs). */
  label: string | null;
  /** This kind's active sources, already sorted by sort_order. */
  sources: SourceSummary[];
  onReorder: (kind: SourceKind, orderedIds: number[]) => void;
  onArchive: (id: number) => void;
}

/**
 * One kind's reorderable item list within a section card. Owns the drag context
 * for its own items so each kind reorders independently (the reorder API is
 * per-kind). Shows a bounded preview with a "+N more" hint and an add control
 * that routes to the detail view in create mode.
 */
export function SourceGroupList({
  kind,
  label,
  sources,
  onReorder,
  onArchive,
}: SourceGroupListProps) {
  const ids = sources.map((source) => source.id);
  const { draggingId, handleProps } = useDragReorder(ids, (nextIds) =>
    onReorder(kind, nextIds as number[]),
  );
  const preview = sources.slice(0, SECTION_PREVIEW_LIMIT);
  const overflow = sources.length - preview.length;

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <span className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
          {label}
        </span>
      )}
      {sources.length === 0 ? (
        <p className="text-muted-foreground text-sm">Nothing here yet.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {preview.map((source) => (
            <SourceItemRow
              key={source.id}
              source={source}
              handleProps={handleProps(source.id)}
              isDragging={draggingId === source.id}
              onArchive={onArchive}
            />
          ))}
        </ul>
      )}
      {overflow > 0 && <span className="text-muted-foreground text-xs">+{overflow} more</span>}
      <Link
        to={`/profile/sources/new?kind=${kind}`}
        className="text-primary inline-flex items-center gap-1 text-sm font-medium hover:underline"
      >
        <Plus className="size-3.5" /> Add {label ? label.toLowerCase() : kind}
      </Link>
    </div>
  );
}
