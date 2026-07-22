import { useCallback, useState } from "react";

import { DEFAULT_SECTION_ORDER, SECTION_ORDER_STORAGE_KEY } from "../constants";
import type { SectionId } from "../types";

/**
 * The section-card order, persisted client-side. There is no backend endpoint
 * for section-card order (unlike per-kind item order, which uses `/sources/reorder`),
 * so this is the pragmatic home for it: a `SectionId[]` in localStorage, keyed
 * once. A stored order is reconciled against the current section set so adding or
 * removing a section never strands the user on a stale list.
 */
export function useSectionOrder(): {
  order: SectionId[];
  reorder: (nextOrder: SectionId[]) => void;
} {
  const [order, setOrder] = useState<SectionId[]>(readOrder);

  const reorder = useCallback((nextOrder: SectionId[]) => {
    const reconciled = reconcile(nextOrder);
    setOrder(reconciled);
    writeOrder(reconciled);
  }, []);

  return { order, reorder };
}

function readOrder(): SectionId[] {
  try {
    const raw = window.localStorage.getItem(SECTION_ORDER_STORAGE_KEY);
    return reconcile(raw ? (JSON.parse(raw) as unknown) : null);
  } catch {
    return [...DEFAULT_SECTION_ORDER];
  }
}

function writeOrder(order: SectionId[]): void {
  try {
    window.localStorage.setItem(SECTION_ORDER_STORAGE_KEY, JSON.stringify(order));
  } catch {
    // A storage failure (private mode, quota) only loses persistence, not the
    // in-memory order, so it is non-fatal and swallowed deliberately.
  }
}

/** Keep valid stored ids in their stored order, then append any missing sections. */
function reconcile(stored: unknown): SectionId[] {
  const valid = new Set<SectionId>(DEFAULT_SECTION_ORDER);
  const kept = Array.isArray(stored)
    ? stored.filter((id): id is SectionId => valid.has(id as SectionId))
    : [];
  const seen = new Set(kept);
  const missing = DEFAULT_SECTION_ORDER.filter((id) => !seen.has(id));
  return [...kept, ...missing];
}
