import { Link } from "react-router";

import { formatDayYear } from "@/lib/formatDate";
import { resumeEditorPath } from "@/lib/resumePaths";
import { Button } from "@/components/ui/button";

import type { JobApplicationSummary } from "../types";
import { JobApplicationStatusBadge } from "./JobApplicationStatusBadge";

interface JobApplicationRowProps {
  application: JobApplicationSummary;
  /** The linked resume's title, resolved by id, or undefined if unknown. */
  resumeTitle: string | undefined;
  /** Open the fork dialog to create this application's resume. */
  onLinkResume: (application: JobApplicationSummary) => void;
  /** Open the confirm gate to mark this application submitted. */
  onSubmit: (application: JobApplicationSummary) => void;
}

/**
 * One job application row: company, role, status, the linked resume (a link that
 * opens it, or a fork action when none is linked yet), and the added date. An
 * `added` application offers "Mark submitted", which finalizes the linked resume.
 *
 * The row action is a ghost control rather than an outlined one so a table of rows
 * reads as one calm surface instead of a stack of boxes.
 */
export function JobApplicationRow({
  application,
  resumeTitle,
  onLinkResume,
  onSubmit,
}: JobApplicationRowProps) {
  return (
    <tr>
      <td className="py-3 pr-4 font-medium">{application.company}</td>
      <td className="text-muted-foreground py-3 pr-4">{application.role_title}</td>
      <td className="py-3 pr-4">
        <JobApplicationStatusBadge status={application.status} />
      </td>
      <td className="py-3 pr-4">
        {application.linked_resume_id !== null ? (
          <Link
            to={resumeEditorPath(application.linked_resume_id)}
            className="text-primary font-medium underline-offset-4 hover:underline"
          >
            {resumeTitle ?? "Open resume"}
          </Link>
        ) : (
          <button
            type="button"
            onClick={() => onLinkResume(application)}
            className="text-primary font-medium underline-offset-4 hover:underline"
          >
            Create resume
          </button>
        )}
      </td>
      <td className="text-muted-foreground mono-meta py-3 pr-4 whitespace-nowrap">
        {formatDayYear(application.created_at)}
      </td>
      <td className="py-3 text-right">
        {application.status === "added" && (
          <Button variant="ghost" size="sm" onClick={() => onSubmit(application)}>
            Mark submitted
          </Button>
        )}
      </td>
    </tr>
  );
}
