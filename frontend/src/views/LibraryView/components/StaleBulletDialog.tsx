import { Modal } from "@/components/Modal";
import { Button } from "@/components/ui/button";

interface StaleBulletDialogProps {
  isOpen: boolean;
  /** Re-read the bullet from the server and reopen the editor on the latest revision. */
  onReread: () => void;
  /** Dismiss without re-reading (the edit was not applied). */
  onDismiss: () => void;
}

/**
 * The recoverable stale-edit prompt for a library bullet. A save was rejected
 * because the bullet changed since it was loaded (a 409 from the optimistic
 * revision guard), so the edit was not applied. The user re-reads the latest
 * revision and retries: the write is never silently overwritten. Mirrors the
 * resume editor's stale-save prompt so both edit paths recover the same way.
 */
export function StaleBulletDialog({ isOpen, onReread, onDismiss }: StaleBulletDialogProps) {
  return (
    <Modal isOpen={isOpen} onClose={onDismiss} title="This bulletpoint changed">
      <p className="text-muted-foreground text-sm">
        Someone (or one of your agents) changed this bulletpoint since you opened it, so your last
        edit was not applied. Re-read the latest version and try again.
      </p>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onDismiss}>
          Dismiss
        </Button>
        <Button onClick={onReread}>Re-read latest</Button>
      </div>
    </Modal>
  );
}
