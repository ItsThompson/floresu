import type { components } from "@/api";

export type ResumeSummary = components["schemas"]["ResumeSummary"];
export type ResumeCreateRequest = components["schemas"]["ResumeCreateRequest"];
export type ResumeKind = components["schemas"]["ResumeKind"];

/** How a new resume is seeded, selected in the new-resume dialog. */
export type SourceMode = "blank" | "duplicate" | "from_resume";

/**
 * The new-resume dialog's controlled form state. `mode` and `sourceId` are
 * UI-intermediate: `buildCreateRequest` maps them to the `ResumeCreateRequest.source`
 * union at submit, so this shape is the form representation, not the write body.
 */
export interface ResumeFormValues {
  title: string;
  mode: SourceMode;
  sourceId: number | null;
}

/** The list load lifecycle. `ready` covers the empty list too. */
export type ResumeListStatus = "loading" | "ready" | "error";

/** Resumes split into the two groups the list renders under separate headings. */
export interface ResumeGroups {
  living: ResumeSummary[];
  application: ResumeSummary[];
}

export interface ResumesListState {
  status: ResumeListStatus;
  groups: ResumeGroups;
  error: string | null;
}

export interface ResumesListActions {
  /** Create a resume per the kind+source contract; resolves to the new id or null on failure. */
  create: (request: ResumeCreateRequest) => Promise<number | null>;
  /** Permanently delete a resume (web-only, confirm-gated); resolves to whether it succeeded. */
  remove: (id: number) => Promise<boolean>;
  /** Re-fetch the list (after an out-of-band change). */
  reload: () => void;
}
