import { Link } from "react-router";

import { resumeEditorPath } from "@/lib/resumePaths";

import type { ResumeSummary } from "../types";
import { ResumeStatusBadge } from "./ResumeStatusBadge";

interface ResumeListRowProps {
  resume: ResumeSummary;
  /** Opens the confirm-gated permanent-delete dialog for this resume. */
  onDelete: (resume: ResumeSummary) => void;
}

/**
 * One resume row: title, lifecycle badge, last-updated time, an open/view link,
 * and web-only permanent delete. A finalized resume is read-only, so its link
 * reads "View" and a note explains that editing needs a fork (done in the editor).
 */
export function ResumeListRow({ resume, onDelete }: ResumeListRowProps) {
  const isFinalized = resume.status === "finalized";
  return (
    <li className="flex items-center gap-3 rounded-md border px-4 py-3">
      <div className="flex flex-1 flex-col gap-1">
        <span className="font-medium">{resume.title}</span>
        <span className="text-muted-foreground text-xs">
          Updated {formatRelativeTime(resume.updated_at)}
          {isFinalized && " · read-only · fork to edit"}
        </span>
      </div>
      <ResumeStatusBadge status={resume.status} />
      <Link
        to={resumeEditorPath(resume.id)}
        className="text-primary text-sm font-medium underline-offset-4 hover:underline"
      >
        {isFinalized ? "View" : "Open"}
      </Link>
      <button
        type="button"
        onClick={() => onDelete(resume)}
        className="text-muted-foreground hover:text-destructive text-sm"
      >
        Delete
      </button>
    </li>
  );
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** A coarse "N days/weeks ago" label; precise timestamps are not needed in the list. */
function formatRelativeTime(iso: string): string {
  const elapsed = Date.now() - new Date(iso).getTime();
  const days = Math.floor(elapsed / DAY_MS);
  if (days <= 0) return "today";
  if (days === 1) return "1 day ago";
  if (days < 7) return `${days} days ago`;
  const weeks = Math.floor(days / 7);
  return weeks === 1 ? "1 week ago" : `${weeks} weeks ago`;
}
