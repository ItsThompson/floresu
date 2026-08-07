import { TriangleAlert } from "lucide-react";

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
 * linked resume permanently, so the ochre hint states that consequence in words
 * immediately before the control that causes it.
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
        submitted finalizes its linked resume. Every referenced library bullet is copied inline as
        read-only text and a frozen PDF is produced, so later library edits can never change what
        you sent.
      </p>
      <p className="bg-warning-tint text-foreground caption flex items-start gap-2 rounded-md px-3 py-2">
        <TriangleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
        This cannot be undone. To change the resume afterward you must fork a new draft copy.
      </p>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button type="button" size="sm" onClick={onConfirm} disabled={isSubmitting}>
          {isSubmitting ? "Submitting…" : "Mark submitted"}
        </Button>
      </div>
    </Modal>
  );
}
