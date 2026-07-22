import type { components } from "@/api";

export type JobApplicationSummary = components["schemas"]["JobApplicationSummary"];
export type JobApplicationStatus = components["schemas"]["JobApplicationStatus"];
export type ResumeSummary = components["schemas"]["ResumeSummary"];

/** The list load lifecycle. `ready` covers the empty list too. */
export type JobApplicationsStatus = "loading" | "ready" | "error";

export interface JobApplicationsState {
  status: JobApplicationsStatus;
  applications: JobApplicationSummary[];
  /** Living resumes offered as the fork source when linking an application resume. */
  livingResumes: ResumeSummary[];
  /** Linked-resume title by id, for the resume column's link label. */
  resumeTitles: Record<number, string>;
  /** Load error (the list could not be fetched). */
  error: string | null;
  /** A recoverable action error (e.g. submit with no linked resume), dismissible. */
  actionError: string | null;
}

export interface JobApplicationsActions {
  /** Re-fetch the list (after an out-of-band change). */
  reload: () => void;
  /** Clear the recoverable action-error banner. */
  dismissActionError: () => void;
  /** Add a job application (company + role title; status starts `added`); resolves to success. */
  create: (company: string, roleTitle: string) => Promise<boolean>;
  /**
   * Fork a living resume into an application `draft` linked 1:1 to the application;
   * resolves to the new resume id, or null on failure.
   */
  linkResume: (
    applicationId: number,
    fromResumeId: number,
    title: string | null,
  ) => Promise<number | null>;
  /**
   * Mark an application `submitted`, which finalizes its linked resume. Resolves to
   * success; a rejection (e.g. no linked resume) leaves the status `added` and
   * surfaces a recoverable message via `actionError`.
   */
  submit: (applicationId: number) => Promise<boolean>;
}

export interface JobApplicationsController {
  state: JobApplicationsState;
  actions: JobApplicationsActions;
}
