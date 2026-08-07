import { TriangleAlert } from "lucide-react";

import { Modal } from "@/components/Modal";
import { Button } from "@/components/ui/button";

interface StaleSaveDialogProps {
  isOpen: boolean;
  /** Re-read the resume from the server and clear the conflict. */
  onReload: () => void;
  /** Dismiss without reloading (the edit was not applied). */
  onDismiss: () => void;
}

/**
 * The recoverable stale-write prompt. A save was rejected because the resume
 * changed since it was loaded (a 409 from the optimistic revision guard), so the
 * edit was not applied. The user re-reads the latest version and retries: the
 * write is never silently overwritten.
 *
 * The prompt is ochre rather than crimson, and carries its message text: nothing
 * was lost and the retry is safe, so this is not a failure.
 */
export function StaleSaveDialog({ isOpen, onReload, onDismiss }: StaleSaveDialogProps) {
  return (
    <Modal isOpen={isOpen} onClose={onDismiss} title="This resume changed">
      <p className="bg-warning-tint text-foreground flex items-start gap-2 rounded-md p-3 text-sm">
        <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
        <span>
          Someone (or one of your agents) changed this resume since you opened it, so your last edit
          was not applied. Re-read the latest version and try again.
        </span>
      </p>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onDismiss}>
          Dismiss
        </Button>
        <Button onClick={onReload}>Re-read latest</Button>
      </div>
    </Modal>
  );
}
