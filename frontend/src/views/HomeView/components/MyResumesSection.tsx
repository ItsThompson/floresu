import { Link } from "react-router";

import { resumeEditorPath } from "@/lib/resumePaths";

import type { HomeSection, ResumeSummary } from "../types";

interface MyResumesSectionProps {
  section: HomeSection<ResumeSummary>;
}

/**
 * The my-resumes region on Home: the account's resumes, each opening its editor.
 * Presentational only; the Home data hook owns the fetch and hands this a
 * per-section status so a failed read blanks this region alone.
 */
export function MyResumesSection({ section }: MyResumesSectionProps) {
  return (
    <section aria-label="My resumes" className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold tracking-tight">My resumes</h2>

      {section.status === "loading" && (
        <p className="text-sm text-muted-foreground">Loading resumes…</p>
      )}

      {section.status === "error" && (
        <p role="alert" className="text-sm text-destructive">
          Could not load your resumes.
        </p>
      )}

      {section.status === "ready" && section.items.length === 0 && (
        <p className="text-sm text-muted-foreground">No resumes yet.</p>
      )}

      {section.status === "ready" && section.items.length > 0 && (
        <ul className="flex flex-col gap-2">
          {section.items.map((resume) => (
            <li
              key={resume.id}
              className="flex items-center justify-between gap-3 rounded-md border px-4 py-3"
            >
              <span className="font-medium">{resume.title}</span>
              <Link
                to={resumeEditorPath(resume.id)}
                className="text-sm font-medium text-primary underline-offset-4 hover:underline"
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
