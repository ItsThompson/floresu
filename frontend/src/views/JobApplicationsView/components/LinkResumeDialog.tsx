import { useState } from "react";

import { Modal } from "@/components/Modal";
import { Button } from "@/components/ui/button";

import type { JobApplicationSummary, ResumeSummary } from "../types";

interface LinkResumeDialogProps {
  /** The application to fork a resume for, or null when the dialog is closed. */
  application: JobApplicationSummary | null;
  /** Living resumes offered as the fork source. */
  livingResumes: ResumeSummary[];
  /** The resumes fetch failed, so the source list is unknown (not necessarily empty). */
  resumesUnavailable: boolean;
  onClose: () => void;
  /** Fork the chosen living resume into an application draft; resolves to the new id or null. */
  onLink: (
    applicationId: number,
    fromResumeId: number,
    title: string | null,
  ) => Promise<number | null>;
  /** Called with the new resume id after a successful fork (the view opens it). */
  onLinked: (resumeId: number) => void;
}

/**
 * Fork a living resume into this application's tailored draft. The fork is a copy
 * linked 1:1 to the application; editing it never changes the source living
 * resume (copy-on-write, enforced on the backend). A failed fork keeps the dialog
 * open with an inline error.
 */
export function LinkResumeDialog({
  application,
  livingResumes,
  resumesUnavailable,
  onClose,
  onLink,
  onLinked,
}: LinkResumeDialogProps) {
  const [sourceId, setSourceId] = useState<number | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setSourceId(null);
    setError(null);
  };

  const submit = async () => {
    if (application === null || sourceId === null) return;
    setIsSubmitting(true);
    setError(null);
    const title = `${application.company} — ${application.role_title}`;
    const newId = await onLink(application.id, sourceId, title);
    setIsSubmitting(false);
    if (newId === null) {
      setError("Could not create the application resume. Please try again.");
      return;
    }
    reset();
    onLinked(newId);
  };

  const close = () => {
    reset();
    onClose();
  };

  const hasLivingResumes = livingResumes.length > 0;
  const canSubmit = !isSubmitting && sourceId !== null;

  return (
    <Modal isOpen={application !== null} onClose={close} title="Create the application resume">
      <p className="text-muted-foreground text-sm">
        Fork a living resume into a tailored copy for this job. Editing the copy never changes the
        living resume you started from.
      </p>

      {hasLivingResumes ? (
        <label className="flex flex-col gap-1.5">
          <span className="text-foreground caption">Fork from</span>
          <select
            className="border-input bg-card text-foreground focus-visible:border-ring focus-visible:ring-ring/50 h-9 rounded-md border px-3 text-sm outline-none focus-visible:ring-[3px]"
            value={sourceId ?? ""}
            onChange={(event) =>
              setSourceId(event.target.value ? Number(event.target.value) : null)
            }
          >
            <option value="">Select a living resume…</option>
            {livingResumes.map((resume) => (
              <option key={resume.id} value={resume.id}>
                {resume.title}
              </option>
            ))}
          </select>
        </label>
      ) : resumesUnavailable ? (
        <p role="alert" className="text-destructive text-sm">
          Couldn’t load your resumes. Close this dialog and try again.
        </p>
      ) : (
        <p className="text-muted-foreground text-sm">
          You have no living resumes yet. Create one first, then fork it for this application.
        </p>
      )}

      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={close}>
          Cancel
        </Button>
        <Button type="button" size="sm" onClick={() => void submit()} disabled={!canSubmit}>
          Create resume
        </Button>
      </div>
    </Modal>
  );
}
