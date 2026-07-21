import type { SectionId, SourceKind } from "./types";

/** localStorage key holding the user's section-card order (a `SectionId[]`). */
export const SECTION_ORDER_STORAGE_KEY = "floresu.profile.sectionOrder";

/** A section card that aggregates one or more source kinds (drill-in to detail). */
export interface SourceSectionConfig {
  id: Extract<SectionId, "work" | "projects" | "education">;
  title: string;
  /** The kinds this card shows, each an independently reorderable group. */
  groups: { kind: SourceKind; label: string | null }[];
}

export const SOURCE_SECTIONS: SourceSectionConfig[] = [
  { id: "work", title: "Work Experience", groups: [{ kind: "role", label: null }] },
  { id: "projects", title: "Projects", groups: [{ kind: "project", label: null }] },
  {
    id: "education",
    title: "Education & Certifications",
    groups: [
      { kind: "education", label: "Education" },
      { kind: "certification", label: "Certifications" },
    ],
  },
];

/** The default top-to-bottom / left-to-right section order before any reorder. */
export const DEFAULT_SECTION_ORDER: SectionId[] = [
  "work",
  "projects",
  "skills",
  "education",
  "identity",
];

/** How many preview items a source card shows before a "+N more" hint. */
export const SECTION_PREVIEW_LIMIT = 4;
