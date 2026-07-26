import { Modal } from "@/components/Modal";
import { Button } from "@/components/ui/button";

import { useItemHistory } from "./hooks/useItemHistory";
import { ItemHistoryRow } from "./ItemHistoryRow";

const LOADING = "Loading history…";
const EMPTY_STATE = "No history yet for this item.";
const LOAD_ERROR = "Could not load history. Close and reopen to retry.";

interface ItemHistoryDialogProps {
  isOpen: boolean;
  onClose: () => void;
  /** The audited entity's type, e.g. `"worklog"` or `"bullet"`. */
  entityType: string;
  /** The audited entity's id. */
  entityId: number;
  /** The dialog heading; defaults to "History". */
  title?: string;
}

/**
 * An entity-agnostic dialog that shows one item's audit trail, newest-first, with
 * each row attributed to its human or agent actor. Reused across surfaces (the
 * worklog overflow menu is the primary one); the caller owns the open state and
 * passes the entity to audit.
 */
export function ItemHistoryDialog({
  isOpen,
  onClose,
  entityType,
  entityId,
  title = "History",
}: ItemHistoryDialogProps) {
  const state = useItemHistory(entityType, entityId, isOpen);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="lg">
      {state.status === "loading" && (
        <p role="status" className="text-sm text-muted-foreground">
          {LOADING}
        </p>
      )}

      {state.status === "error" && (
        <p role="alert" className="text-sm text-destructive">
          {LOAD_ERROR}
        </p>
      )}

      {state.status === "ready" && state.entries.length === 0 && (
        <p className="text-sm text-muted-foreground">{EMPTY_STATE}</p>
      )}

      {state.status === "ready" && state.entries.length > 0 && (
        <ul className="flex max-h-[60vh] flex-col gap-2 overflow-auto">
          {state.entries.map((entry) => (
            <ItemHistoryRow key={entry.id} entry={entry} />
          ))}
        </ul>
      )}

      <div className="flex justify-end">
        <Button variant="outline" onClick={onClose}>
          Close
        </Button>
      </div>
    </Modal>
  );
}
