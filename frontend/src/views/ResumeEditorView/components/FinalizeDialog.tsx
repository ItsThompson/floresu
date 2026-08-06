import { TriangleAlert } from "lucide-react";

import { Modal } from "@/components/Modal";
import { Button } from "@/components/ui/button";

interface FinalizeDialogProps {
  isOpen: boolean;
  /** True while the finalize request is in flight; disables both actions. */
  isFinalizing: boolean;
  /** Freeze the resume permanently (and submit a linked application). */
  onConfirm: () => void;
  /** Close without finalizing. */
  onCancel: () => void;
}

/**
 * The finalize confirm gate. Finalizing is permanent, so the user must confirm
 * after reading what freezing does: every library reference is copied inline as
 * read-only text and the identity is snapshotted, a frozen PDF is produced, and a
 * linked job application is marked submitted. The only way to change a finalized
 * resume afterward is to fork a new draft.
 *
 * The gate is ochre, not crimson: nothing here has failed, the step is simply one
 * the user cannot take back. It states that in words, so the tint never has to.
 */
export function FinalizeDialog({ isOpen, isFinalizing, onConfirm, onCancel }: FinalizeDialogProps) {
  return (
    <Modal isOpen={isOpen} onClose={onCancel} title="Finalize this resume?">
      <p className="bg-warning-tint text-foreground flex items-start gap-2 rounded-md p-3 text-sm">
        <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
        <span>
          Finalizing freezes this application resume <strong>permanently</strong>. Every referenced
          library bullet is copied inline as read-only text and the contact identity is snapshotted,
          so later library edits can never change it. A frozen PDF is produced and any linked job
          application is marked submitted. This cannot be undone: to change it afterward you must
          fork a new draft copy.
        </span>
      </p>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel} disabled={isFinalizing}>
          Cancel
        </Button>
        <Button onClick={onConfirm} disabled={isFinalizing}>
          {isFinalizing ? "Finalizing…" : "Finalize permanently"}
        </Button>
      </div>
    </Modal>
  );
}
