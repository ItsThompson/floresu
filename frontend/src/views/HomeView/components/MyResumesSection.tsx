import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { RESUMES_PATH, resumeEditorPath } from "@/lib/resumePaths";

import type { HomeSection, ResumeSummary } from "../types";

interface MyResumesSectionProps {
  section: HomeSection<ResumeSummary>;
}

/**
 * The my-resumes region on Home: the account's resumes, each opening its editor.
 * Presentational only; the Home data hook owns the fetch and hands this a
 * per-section status so a failed read blanks this region alone.
 *
 * A calm card throughout, including its empty state: the serif display moment on
 * Home belongs to the worklog region, since a record comes before a resume.
 */
export function MyResumesSection({ section }: MyResumesSectionProps) {
  return (
    <section
      aria-label="My resumes"
      className="bg-card text-card-foreground border-border flex flex-col gap-3 rounded-lg border p-6"
    >
      <h2 className="text-lg font-semibold tracking-tight">My resumes</h2>

      {section.status === "loading" && (
        <p className="text-muted-foreground text-sm">Loading resumes…</p>
      )}

      {section.status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          Could not load your resumes.
        </p>
      )}

      {section.status === "ready" && section.items.length === 0 && (
        <div className="flex flex-col items-start gap-3">
          <p className="font-medium">Shape one when you need it.</p>
          <p className="text-muted-foreground text-sm">No resumes yet.</p>
          <Button asChild>
            <Link to={RESUMES_PATH}>Start a resume</Link>
          </Button>
        </div>
      )}

      {section.status === "ready" && section.items.length > 0 && (
        <ul className="flex flex-col gap-2">
          {section.items.map((resume) => (
            <li key={resume.id} className="flex items-center justify-between gap-3">
              <span className="truncate font-medium">{resume.title}</span>
              <Link
                to={resumeEditorPath(resume.id)}
                className="text-primary shrink-0 text-sm font-medium underline-offset-4 hover:underline"
              >
                Open
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
