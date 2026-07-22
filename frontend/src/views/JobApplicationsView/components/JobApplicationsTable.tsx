import type { JobApplicationSummary } from "../types";
import { JobApplicationRow } from "./JobApplicationRow";

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
        <tr className="text-muted-foreground border-b text-xs font-medium tracking-wide uppercase">
          <th scope="col" className="py-2 pr-4 font-medium">
            Company
          </th>
          <th scope="col" className="py-2 pr-4 font-medium">
            Role
          </th>
          <th scope="col" className="py-2 pr-4 font-medium">
            Status
          </th>
          <th scope="col" className="py-2 pr-4 font-medium">
            Resume
          </th>
          <th scope="col" className="py-2 pr-4 font-medium">
            Added
          </th>
          <th scope="col" className="py-2 text-right font-medium">
            <span className="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
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
