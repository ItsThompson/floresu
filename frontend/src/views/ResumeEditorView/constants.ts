import type { components } from "@/api";

type SectionKind = components["schemas"]["SectionKind"];

/** How long after a save the live preview waits before it re-renders. */
export const PREVIEW_DEBOUNCE_MS = 500;

/** Human labels for the fixed section kinds, used as fallback section titles. */
export const SECTION_KIND_LABEL: Record<SectionKind, string> = {
  work: "Work Experience",
  projects: "Projects",
  education: "Education",
  skills: "Skills",
  certifications: "Certifications",
  summary: "Summary",
  custom: "Section",
};
