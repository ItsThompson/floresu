import type { ResumeSummary } from "../types";
import { ResumeListRow } from "./ResumeListRow";

interface ResumeGroupSectionProps {
  heading: string;
  /** Shown under the heading when the group is empty. */
  emptyMessage: string;
  resumes: ResumeSummary[];
  onDelete: (resume: ResumeSummary) => void;
}

/**
 * One titled group in the resumes list (Living or Applications): a heading plus
 * the rows, or an encouraging empty message when the group has no resumes yet.
 */
export function ResumeGroupSection({
  heading,
  emptyMessage,
  resumes,
  onDelete,
}: ResumeGroupSectionProps) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-muted-foreground caption">{heading}</h2>
      {resumes.length === 0 ? (
        <p className="text-muted-foreground text-sm">{emptyMessage}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {resumes.map((resume) => (
            <ResumeListRow key={resume.id} resume={resume} onDelete={onDelete} />
          ))}
        </ul>
      )}
    </section>
  );
}
