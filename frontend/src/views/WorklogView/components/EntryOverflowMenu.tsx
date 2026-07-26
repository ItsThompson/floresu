import { useState } from "react";
import { Link } from "react-router";

import { ItemHistoryDialog } from "@/components/ItemHistoryDialog";
import { Button } from "@/components/ui/button";

import { libraryBulletHref } from "../constants";
import { useDerivedBullets } from "../hooks/useDerivedBullets";

interface EntryOverflowMenuProps {
  entryId: number;
  entryTitle: string;
  onEdit: () => void;
  onArchive: () => void;
}

/**
 * The per-row overflow menu: edit, archive, and the bullets derived from this
 * entry. The derived bullets load lazily (only while the menu is open) and each
 * links into the Library, where the bullet is framed.
 */
export function EntryOverflowMenu({ entryId, entryTitle, onEdit, onArchive }: EntryOverflowMenuProps) {
  const [open, setOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const derived = useDerivedBullets(open ? entryId : null);

  return (
    <div className="relative">
      <button
        type="button"
        aria-label={`Actions for ${entryTitle}`}
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
        className="hover:bg-accent rounded-md px-2 py-1 text-sm leading-none"
      >
        ⋯
      </button>

      {open && (
        <div className="bg-popover text-popover-foreground absolute right-0 z-10 mt-1 flex w-64 flex-col gap-2 rounded-md border p-2 shadow-md">
          <div className="flex flex-col">
            <Button
              variant="ghost"
              size="sm"
              className="justify-start"
              onClick={() => {
                setOpen(false);
                onEdit();
              }}
            >
              Edit
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="justify-start"
              onClick={() => {
                setOpen(false);
                onArchive();
              }}
            >
              Archive
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="justify-start"
              onClick={() => {
                setOpen(false);
                setHistoryOpen(true);
              }}
            >
              History
            </Button>
          </div>

          <div className="border-t pt-2">
            <p className="text-muted-foreground px-2 pb-1 text-xs font-medium">Derived bullets</p>
            {derived.status === "loading" && (
              <p className="text-muted-foreground px-2 text-xs">Loading…</p>
            )}
            {derived.status === "error" && (
              <p className="text-destructive px-2 text-xs">Could not load derived bullets.</p>
            )}
            {derived.status === "ready" && derived.bullets.length === 0 && (
              <p className="text-muted-foreground px-2 text-xs">No bullets frame this entry yet.</p>
            )}
            {derived.bullets.length > 0 && (
              <ul className="flex flex-col">
                {derived.bullets.map((bullet) => (
                  <li key={bullet.id}>
                    <Link
                      to={libraryBulletHref(bullet.id)}
                      className="hover:bg-accent block truncate rounded-md px-2 py-1 text-xs"
                    >
                      {bullet.text}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      <ItemHistoryDialog
        isOpen={historyOpen}
        onClose={() => setHistoryOpen(false)}
        entityType="worklog"
        entityId={entryId}
        title={`History: ${entryTitle}`}
      />
    </div>
  );
}
