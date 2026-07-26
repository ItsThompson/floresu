import type { ResumeItem, ResumeRecord, ResumeSection, ResumeUpdate, SectionKind } from "./types";

/** Mint a fresh section id, unique within the document (section ids are client-minted in this contract). */
function mintSectionId(): string {
  return `sec-${crypto.randomUUID()}`;
}

/** Append an empty section with a fresh id and return the full-document write body. */
export function withNewSection(record: ResumeRecord, kind: SectionKind, title: string): ResumeUpdate {
  const section: ResumeSection = { id: mintSectionId(), kind, title, item_order: [], items: {} };
  const sections = [...(record.document.sections ?? []), section];
  return toResumeUpdate(record, { sections });
}

/** Build the full-document write body from a record, with optional field overrides. */
export function toResumeUpdate(record: ResumeRecord, overrides?: Partial<ResumeUpdate>): ResumeUpdate {
  const { document } = record;
  return {
    title: record.title,
    template_id: document.template_id,
    header: document.header,
    sections: document.sections,
    ...overrides,
  };
}

/**
 * Return a write body with one local item's text replaced. Only local items are
 * edited directly; a library_ref item's text lives on the canonical bullet and is
 * changed through the scope flow, never here.
 */
export function withLocalItemText(record: ResumeRecord, itemId: string, newText: string): ResumeUpdate {
  const sections = (record.document.sections ?? []).map((section) => {
    const item = section.items?.[itemId];
    if (!item || item.kind !== "local") return section;
    return { ...section, items: { ...section.items, [itemId]: { ...item, text: newText } } };
  });
  return toResumeUpdate(record, { sections });
}

/** The ordered items of a section, resolved from its id-keyed map and order list. */
export function orderedItems(section: ResumeSection): ResumeItem[] {
  const items = section.items ?? {};
  const order = section.item_order ?? Object.keys(items);
  return order.reduce<ResumeItem[]>((acc, id) => {
    const item = items[id];
    if (item) acc.push(item);
    return acc;
  }, []);
}

/** Move the id at `fromIndex` to `toIndex`, returning a new ordered array. */
export function moveInOrder(order: string[], fromIndex: number, toIndex: number): string[] {
  if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0) return order;
  if (fromIndex >= order.length || toIndex >= order.length) return order;
  const next = [...order];
  const [moved] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moved);
  return next;
}
