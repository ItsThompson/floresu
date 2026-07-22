import { Modal } from "@/components/Modal";
import { Button } from "@/components/ui/button";

import type { JobApplicationSummary } from "../types";

interface SubmitConfirmDialogProps {
  /** The application to mark submitted, or null when the dialog is closed. */
  application: JobApplicationSummary | null;
  /** True while the submit request is in flight; disables both actions. */
  isSubmitting: boolean;
  /** Mark the application submitted (finalizes its linked resume). */
  onConfirm: () => void;
  /** Close without submitting. */
  onCancel: () => void;
}

/**
 * The mark-submitted confirm gate. Marking an application submitted finalizes its
 * linked resume, which is permanent, so the user must confirm after reading what
 * freezing does: every referenced library bullet is copied inline as read-only
 * text and a frozen PDF is produced. This cannot be undone; to change the resume
 * afterward you must fork a new draft.
 */
export function SubmitConfirmDialog({
  application,
  isSubmitting,
  onConfirm,
  onCancel,
}: SubmitConfirmDialogProps) {
  return (
    <Modal
      isOpen={application !== null}
      onClose={onCancel}
      title="Mark this application submitted?"
    >
      <p className="text-muted-foreground text-sm">
        Marking {application ? <strong>{application.company}</strong> : "this application"}{" "}
        submitted finalizes its linked resume <strong>permanently</strong>. Every referenced library
        bullet is copied inline as read-only text and a frozen PDF is produced, so later library
        edits can never change what you sent. This cannot be undone: to change it afterward you must
        fork a new draft copy.
      </p>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button onClick={onConfirm} disabled={isSubmitting}>
          {isSubmitting ? "Submitting…" : "Mark submitted"}
        </Button>
      </div>
    </Modal>
  );
}
