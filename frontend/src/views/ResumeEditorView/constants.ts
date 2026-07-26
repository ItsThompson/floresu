import type { SectionKind } from "./types";

/** How long after a save the live preview waits before it re-renders. */
export const PREVIEW_DEBOUNCE_MS = 500;

/** The section kinds the add-section control offers, each with its default title. */
export const SECTION_KIND_OPTIONS: readonly { kind: SectionKind; label: string }[] = [
  { kind: "work", label: "Work Experience" },
  { kind: "projects", label: "Projects" },
  { kind: "education", label: "Education" },
  { kind: "skills", label: "Skills" },
  { kind: "certifications", label: "Certifications" },
  { kind: "summary", label: "Summary" },
];

/** The kind the add-section control starts on. */
export const DEFAULT_SECTION_KIND: SectionKind = "work";

/** The default title for a section kind, used as the add-section placeholder and blank-title fallback. */
export function sectionKindLabel(kind: SectionKind): string {
  return SECTION_KIND_OPTIONS.find((option) => option.kind === kind)?.label ?? kind;
}
