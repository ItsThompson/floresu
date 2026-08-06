import type { JobApplicationSummary } from "../types";
import { JobApplicationRow } from "./JobApplicationRow";

/**
 * `caption` sits on the cell rather than the header row because the browser's own
 * `th` rule sets a bold weight, which an inherited weight would not override.
 */
const HEADER_CELL = "caption py-2 pr-4";

interface JobApplicationsTableProps {
  applications: JobApplicationSummary[];
  /** Linked-resume titles by id, for each row's resume link. */
  resumeTitles: Record<number, string>;
  onLinkResume: (application: JobApplicationSummary) => void;
  onSubmit: (application: JobApplicationSummary) => void;
}

/**
 * The job applications table: company, role, status, linked resume, and added
 * date, one row per application. Presentational only; row intent is delegated up.
 */
export function JobApplicationsTable({
  applications,
  resumeTitles,
  onLinkResume,
  onSubmit,
}: JobApplicationsTableProps) {
  return (
    <table className="w-full border-collapse text-left">
      <thead>
        <tr className="text-muted-foreground border-border/60 border-b">
          <th scope="col" className={HEADER_CELL}>
            Company
          </th>
          <th scope="col" className={HEADER_CELL}>
            Role
          </th>
          <th scope="col" className={HEADER_CELL}>
            Status
          </th>
          <th scope="col" className={HEADER_CELL}>
            Resume
          </th>
          <th scope="col" className={HEADER_CELL}>
            Added
          </th>
          <th scope="col" className="caption py-2 text-right">
            <span className="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody className="divide-border/60 divide-y text-sm">
        {applications.map((application) => (
          <JobApplicationRow
            key={application.id}
            application={application}
            resumeTitle={
              application.linked_resume_id === null
                ? undefined
                : resumeTitles[application.linked_resume_id]
            }
            onLinkResume={onLinkResume}
            onSubmit={onSubmit}
          />
        ))}
      </tbody>
    </table>
  );
}
