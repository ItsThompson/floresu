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
 */
export function FinalizeDialog({ isOpen, isFinalizing, onConfirm, onCancel }: FinalizeDialogProps) {
  return (
    <Modal isOpen={isOpen} onClose={onCancel} title="Finalize this resume?">
      <p className="text-muted-foreground text-sm">
        Finalizing freezes this application resume <strong>permanently</strong>. Every referenced
        library bullet is copied inline as read-only text and the contact identity is snapshotted,
        so later library edits can never change it. A frozen PDF is produced and any linked job
        application is marked submitted. This cannot be undone: to change it afterward you must fork
        a new draft copy.
      </p>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel} disabled={isFinalizing}>
          Cancel
        </Button>
        <Button onClick={onConfirm} disabled={isFinalizing}>
          {isFinalizing ? "Finalizing…" : "Finalize permanently"}
        </Button>
      </div>
    </Modal>
  );
}
