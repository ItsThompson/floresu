import { useDragList } from "../hooks/useDragList";
import type {
  BulletpointRecord,
  IdentityVariant,
  ResumeEditorActions,
  ResumeRecord,
} from "../types";
import { AddSectionControl } from "./AddSectionControl";
import { HeaderSection } from "./HeaderSection";
import { SectionCard } from "./SectionCard";

interface SectionFormProps {
  record: ResumeRecord;
  bulletsById: Record<number, BulletpointRecord>;
  allBullets: BulletpointRecord[];
  variants: IdentityVariant[];
  isReadOnly: boolean;
  actions: ResumeEditorActions;
}

/**
 * The editor's left column: the identity header plus the ordered, drag-reorderable
 * sections. Sections reorder by drag here; each section owns its own item order.
 * Pure composition: it wires the record and the editor actions to the section
 * cards and holds no write logic of its own.
 */
export function SectionForm({
  record,
  bulletsById,
  allBullets,
  variants,
  isReadOnly,
  actions,
}: SectionFormProps) {
  const sections = record.document.sections ?? [];
  const sectionIds = sections.map((section) => section.id);
  const sectionDrag = useDragList(sectionIds, actions.reorderSections);

  return (
    <div className="flex flex-col gap-4">
      <HeaderSection
        variants={variants}
        selectedVariantId={record.document.header?.identity_variant_id}
        isReadOnly={isReadOnly}
        onSelect={actions.setIdentityVariant}
      />

      {sections.map((section, index) => (
        <SectionCard
          key={section.id}
          section={section}
          bulletsById={bulletsById}
          allBullets={allBullets}
          isReadOnly={isReadOnly}
          onEditText={actions.editItemText}
          onRemoveItem={actions.removeItem}
          onPromoteItem={actions.promoteItem}
          onAddLibraryItem={actions.addLibraryItem}
          onAddInline={actions.addInlineItem}
          onReorderItems={actions.reorderItems}
          drag={isReadOnly ? undefined : sectionDrag.handlers(index)}
        />
      ))}

      {!isReadOnly && <AddSectionControl onAddSection={actions.addSection} />}
    </div>
  );
}
