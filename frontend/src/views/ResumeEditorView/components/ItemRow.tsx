import { useState } from "react";
import { GripVertical, Trash2 } from "lucide-react";

import type { BulletpointRecord, ResumeItem } from "../types";
import { SharedMarker } from "./SharedMarker";

interface DragBinding {
  draggable: true;
  onDragStart: () => void;
  onDragOver: (event: React.DragEvent) => void;
  onDrop: () => void;
  onDragEnd: () => void;
}

interface ItemRowProps {
  item: ResumeItem;
  /** Resolved canonical bullet for a library_ref item (carries text + usage count). */
  bullet?: BulletpointRecord;
  isReadOnly: boolean;
  onEditText: (item: ResumeItem, newText: string) => void;
  onRemove: (itemId: string) => void;
  onPromote: (itemId: string) => void;
  /** Native drag handlers from the section's drag list (omitted when read-only). */
  drag?: DragBinding;
}

/**
 * One editable item row: a drag handle, the bullet text, a shared marker, and
 * remove/promote controls. A library_ref shows the resolved canonical text and a
 * ⚑ "used in N" marker when shared; editing it runs the copy-on-write scope flow.
 * A local item edits its own text directly and can be promoted to the library. A
 * finalized resume renders read-only (no edit, drag, or remove).
 */
export function ItemRow({ item, bullet, isReadOnly, onEditText, onRemove, onPromote, drag }: ItemRowProps) {
  const resolvedText = item.kind === "local" ? item.text : (bullet?.text ?? "…");
  const usedIn = bullet?.used_in_count ?? 0;
  const isShared = item.kind === "library_ref" && usedIn >= 2;

  const [draft, setDraft] = useState(resolvedText);
  const [lastText, setLastText] = useState(resolvedText);
  if (resolvedText !== lastText) {
    // Adopt an externally changed value (e.g. after an "everywhere" edit).
    setLastText(resolvedText);
    setDraft(resolvedText);
  }

  const commit = () => {
    const next = draft.trim();
    if (next && next !== resolvedText) onEditText(item, next);
  };

  if (isReadOnly) {
    return (
      <li className="flex items-start gap-2 rounded-md border px-3 py-2 text-sm">
        <span className="flex-1">{resolvedText}</span>
        {isShared && <SharedMarker usedIn={usedIn} />}
      </li>
    );
  }

  return (
    <li className="flex items-start gap-2 rounded-md border px-3 py-2 text-sm">
      <button
        type="button"
        aria-label="Drag to reorder item"
        className="text-muted-foreground mt-0.5 cursor-grab"
        {...drag}
      >
        <GripVertical aria-hidden className="size-4" />
      </button>

      <textarea
        aria-label="Bullet text"
        rows={2}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        className="border-input bg-background focus-visible:ring-ring/50 flex-1 resize-y rounded-md border px-2 py-1 outline-none focus-visible:ring-[2px]"
      />

      <div className="flex flex-col items-end gap-1">
        {isShared && <SharedMarker usedIn={usedIn} />}
        {item.kind === "local" && (
          <button
            type="button"
            onClick={() => onPromote(item.id)}
            className="text-muted-foreground hover:text-primary text-xs"
          >
            Promote
          </button>
        )}
        <button
          type="button"
          aria-label="Remove item"
          onClick={() => onRemove(item.id)}
          className="text-muted-foreground hover:text-destructive"
        >
          <Trash2 aria-hidden className="size-4" />
        </button>
      </div>
    </li>
  );
}
