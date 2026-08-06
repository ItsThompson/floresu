import { useState } from "react";

import { isSameArchivedItem } from "../constants";
import { useArchive } from "../hooks/useArchive";
import type { ArchivedItem } from "../types";
import { ArchivedItemRow } from "./ArchivedItemRow";
import { ConfirmDestructiveDialog } from "./ConfirmDestructiveDialog";
import { SettingsPanel } from "./SettingsPanel";

/**
 * The Archive & Trash section: archived worklog entries, sources, and bullets
 * with restore and permanent delete. Restore returns an item to its active views
 * (and, where applicable, search). Permanent delete is web-only, irreversible,
 * and gated behind an explicit acknowledgement in the confirmation dialog; no
 * agent has this capability.
 */
export function ArchivePanel() {
  const { state, actions } = useArchive();
  const [pendingDelete, setPendingDelete] = useState<ArchivedItem | null>(null);

  const confirmDelete = () => {
    if (!pendingDelete) return;
    actions.permanentlyDelete(pendingDelete);
    setPendingDelete(null);
  };

  const isPending = (item: ArchivedItem): boolean =>
    state.pending !== null && isSameArchivedItem(state.pending, item);

  return (
    <>
      <SettingsPanel
        title="Archive & Trash"
        description="Restore an archived item, or permanently delete it. Permanent delete cannot be undone and is available only here in the web app."
      >
        {state.status === "loading" && (
          <p className="text-muted-foreground text-sm">Loading archived items…</p>
        )}
        {state.status === "error" && (
          <p role="alert" className="text-destructive text-sm">
            {state.loadError}
          </p>
        )}
        {state.status === "ready" && state.items.length === 0 && (
          <p className="text-muted-foreground text-sm">Nothing is archived.</p>
        )}
        {state.status === "ready" && state.items.length > 0 && (
          <ul className="divide-border/60 flex flex-col divide-y">
            {state.items.map((item) => (
              <ArchivedItemRow
                key={`${item.entityType}-${item.id}`}
                item={item}
                isPending={isPending(item)}
                onRestore={() => actions.restore(item)}
                onDelete={() => setPendingDelete(item)}
              />
            ))}
          </ul>
        )}
        {state.actionError && (
          <p role="alert" className="text-destructive text-sm">
            {state.actionError}
          </p>
        )}
      </SettingsPanel>

      {pendingDelete && (
        <ConfirmDestructiveDialog
          title="Permanently delete this item?"
          description={`“${pendingDelete.label}” will be removed for good. This cannot be undone.`}
          confirmLabel="Delete permanently"
          acknowledgeLabel="I understand this permanently deletes the item and cannot be undone."
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </>
  );
}
