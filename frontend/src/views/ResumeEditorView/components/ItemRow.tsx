import { useState } from "react";
import { GripVertical, Trash2 } from "lucide-react";

import { FormTextareaField } from "@/components/FormInputField";
import { Button } from "@/components/ui/button";

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
 * "used in N" marker when shared; editing it runs the copy-on-write scope flow. A
 * local item edits its own text directly and can be promoted to the library. A
 * finalized resume renders read-only (no edit, drag, or remove).
 *
 * The row draws no frame of its own: the field carries the only border, and the
 * hairline between rows comes from the list. Its label is present but off screen,
 * because one drawn label per row is noise on the densest surface in the app.
 */
export function ItemRow({
  item,
  bullet,
  isReadOnly,
  onEditText,
  onRemove,
  onPromote,
  drag,
}: ItemRowProps) {
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
      <li className="flex items-start gap-2 py-2.5 text-sm">
        <span className="text-foreground flex-1">{resolvedText}</span>
        {isShared && <SharedMarker usedIn={usedIn} />}
      </li>
    );
  }

  return (
    <li className="flex items-start gap-2 py-2.5">
      <button
        type="button"
        aria-label="Drag to reorder item"
        className="text-muted-foreground mt-2.5 cursor-grab"
        {...drag}
      >
        <GripVertical aria-hidden className="size-4" />
      </button>

      <div className="min-w-0 flex-1">
        <FormTextareaField
          label="Bullet text"
          labelVisibility="hidden"
          rows={2}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
        />
      </div>

      <div className="flex flex-col items-end gap-1">
        {isShared && <SharedMarker usedIn={usedIn} />}
        {item.kind === "local" && (
          <Button type="button" variant="ghost" size="sm" onClick={() => onPromote(item.id)}>
            Promote
          </Button>
        )}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Remove item"
          onClick={() => onRemove(item.id)}
        >
          <Trash2 aria-hidden />
        </Button>
      </div>
    </li>
  );
}
