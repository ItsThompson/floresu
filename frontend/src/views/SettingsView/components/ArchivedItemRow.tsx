import { ArchiveRestore, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";

import { ENTITY_TYPE_LABEL, formatDate } from "../constants";
import type { ArchivedItem } from "../types";

interface ArchivedItemRowProps {
  item: ArchivedItem;
  isPending: boolean;
  onRestore: () => void;
  onDelete: () => void;
}

/**
 * One archived item: its kind, label, and archived date, with Restore and a
 * permanent-delete control. Restore returns it to active views; delete is
 * destructive, so it carries a `trash-2` icon and a label and is confirm-gated by
 * the panel. Both controls disable while an action on this item is in flight.
 */
export function ArchivedItemRow({ item, isPending, onRestore, onDelete }: ArchivedItemRowProps) {
  return (
    <li className="border-border flex items-center gap-3 rounded-md border p-3">
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate font-medium">{item.label}</span>
        <span className="text-muted-foreground text-xs">
          {ENTITY_TYPE_LABEL[item.entityType]} · archived {formatDate(item.archivedAt)}
        </span>
      </div>
      <Button variant="outline" size="sm" onClick={onRestore} disabled={isPending}>
        <ArchiveRestore aria-hidden />
        Restore
      </Button>
      <Button variant="destructive" size="sm" onClick={onDelete} disabled={isPending}>
        <Trash2 aria-hidden />
        Delete
      </Button>
    </li>
  );
}
