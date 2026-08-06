import { Trash2 } from "lucide-react";
import { useState } from "react";

import { Modal } from "@/components/Modal";
import { Button } from "@/components/ui/button";

import type { ResumeSummary } from "../types";

interface DeleteResumeDialogProps {
  /** The resume pending deletion, or null when the dialog is closed. */
  resume: ResumeSummary | null;
  onClose: () => void;
  /** Permanently delete; resolves to whether it succeeded. */
  onConfirm: (id: number) => Promise<boolean>;
}

/**
 * Confirm-gated permanent delete. This action is web-only (never exposed to an
 * agent) and irreversible, so the dialog states that plainly and only fires the
 * delete on an explicit confirmation click.
 *
 * The confirm button pairs its crimson with a bin glyph and a label, so the
 * consequence is never carried by color alone.
 */
export function DeleteResumeDialog({ resume, onClose, onConfirm }: DeleteResumeDialogProps) {
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const confirm = async () => {
    if (!resume) return;
    setIsDeleting(true);
    setError(null);
    const ok = await onConfirm(resume.id);
    setIsDeleting(false);
    if (!ok) {
      setError("Could not delete the resume. Please try again.");
      return;
    }
    onClose();
  };

  return (
    <Modal isOpen={resume !== null} onClose={onClose} title="Delete resume permanently?">
      <p className="text-muted-foreground text-sm">
        {resume ? `"${resume.title}" ` : "This resume "}
        will be permanently deleted. This cannot be undone.
      </p>

      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button
          type="button"
          variant="destructive"
          size="sm"
          onClick={() => void confirm()}
          disabled={isDeleting}
        >
          <Trash2 aria-hidden />
          Delete permanently
        </Button>
      </div>
    </Modal>
  );
}
