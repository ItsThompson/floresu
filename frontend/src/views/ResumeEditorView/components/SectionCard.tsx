import { useState } from "react";
import { ChevronDown, ChevronRight, GripVertical } from "lucide-react";

import { orderedItems } from "../documentOps";
import { useDragList } from "../hooks/useDragList";
import type { BulletpointRecord, ResumeItem, ResumeSection } from "../types";
import { AddItemControls } from "./AddItemControls";
import { ItemRow } from "./ItemRow";
import { LibraryPickerDialog } from "./LibraryPickerDialog";

interface DragBinding {
  draggable: true;
  onDragStart: () => void;
  onDragOver: (event: React.DragEvent) => void;
  onDrop: () => void;
  onDragEnd: () => void;
}

interface SectionCardProps {
  section: ResumeSection;
  bulletsById: Record<number, BulletpointRecord>;
  /** All available canonical bullets, offered by the library picker. */
  allBullets: BulletpointRecord[];
  isReadOnly: boolean;
  onEditText: (item: ResumeItem, newText: string) => void;
  onRemoveItem: (itemId: string) => void;
  onPromoteItem: (itemId: string) => void;
  onAddLibraryItem: (sectionId: string, bulletId: number) => void;
  onAddInline: (sectionId: string, text: string) => void;
  onReorderItems: (sectionId: string, orderedItemIds: string[]) => void;
  /** Native drag handlers for reordering this section among its siblings. */
  drag?: DragBinding;
}

/**
 * One collapsible, drag-reorderable resume section: a header (drag handle,
 * collapse toggle, title) over its ordered item rows and the add controls. Items
 * reorder by drag within the section; a finalized resume renders read-only.
 */
export function SectionCard({
  section,
  bulletsById,
  allBullets,
  isReadOnly,
  onEditText,
  onRemoveItem,
  onPromoteItem,
  onAddLibraryItem,
  onAddInline,
  onReorderItems,
  drag,
}: SectionCardProps) {
  const [isOpen, setIsOpen] = useState(true);
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const items = orderedItems(section);
  const itemIds = items.map((item) => item.id);
  const itemDrag = useDragList(itemIds, (nextIds) => onReorderItems(section.id, nextIds));

  return (
    <section className="rounded-md border">
      <div className="flex items-center gap-2 border-b px-3 py-2">
        {!isReadOnly && (
          <button type="button" aria-label="Drag to reorder section" className="text-muted-foreground cursor-grab" {...drag}>
            <GripVertical aria-hidden className="size-4" />
          </button>
        )}
        <button
          type="button"
          onClick={() => setIsOpen((open) => !open)}
          aria-expanded={isOpen}
          className="flex flex-1 items-center gap-2 text-left font-medium"
        >
          {isOpen ? <ChevronDown aria-hidden className="size-4" /> : <ChevronRight aria-hidden className="size-4" />}
          {section.title}
        </button>
      </div>

      {isOpen && (
        <div className="flex flex-col gap-3 p-3">
          {items.length === 0 ? (
            <p className="text-muted-foreground text-sm">No items yet.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {items.map((item, index) => (
                <ItemRow
                  key={item.id}
                  item={item}
                  bullet={item.kind === "library_ref" ? bulletsById[item.bullet_id] : undefined}
                  isReadOnly={isReadOnly}
                  onEditText={onEditText}
                  onRemove={onRemoveItem}
                  onPromote={onPromoteItem}
                  drag={isReadOnly ? undefined : itemDrag.handlers(index)}
                />
              ))}
            </ul>
          )}

          {!isReadOnly && (
            <AddItemControls
              onPullFromLibrary={() => setIsPickerOpen(true)}
              onAddInline={(text) => onAddInline(section.id, text)}
            />
          )}
        </div>
      )}

      <LibraryPickerDialog
        isOpen={isPickerOpen}
        onClose={() => setIsPickerOpen(false)}
        bullets={allBullets}
        onSelect={(bulletId) => {
          onAddLibraryItem(section.id, bulletId);
          setIsPickerOpen(false);
        }}
      />
    </section>
  );
}
