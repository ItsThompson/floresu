import type { components } from "@/api";

export type SourceSummary = components["schemas"]["SourceSummary"];
export type SourceKind = components["schemas"]["SourceKind"];
export type SkillRead = components["schemas"]["SkillRead"];
export type IdentityVariantRead = components["schemas"]["IdentityVariantRead"];

/** The fixed set of profile sections the hub renders as cards. */
export type SectionId = "work" | "projects" | "skills" | "education" | "identity";

export type HubStatus = "loading" | "ready" | "error";

export interface HubData {
  /** Active sources across every kind; grouped per card in the component. */
  sources: SourceSummary[];
  /** Active, curated skills with their derived usage counts. */
  skills: SkillRead[];
  /** Active identity variants; exactly one carries `is_default`. */
  variants: IdentityVariantRead[];
}

export interface ProfileHubState {
  status: HubStatus;
  data: HubData;
  /** A non-fatal action error (a failed reorder/archive), surfaced as a banner. */
  actionError: string | null;
}

export interface ProfileHubActions {
  /** Persist a new order for one source kind (independent per kind). */
  reorderSources: (kind: SourceKind, orderedIds: number[]) => void;
  /** Archive a source: removes it from active lists, preserving its links. */
  archiveSource: (id: number) => void;
  dismissError: () => void;
}
