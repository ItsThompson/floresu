import { MoreHorizontal, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import { ItemHistoryDialog } from "@/components/ItemHistoryDialog";
import { Button } from "@/components/ui/button";
import { libraryBulletHref } from "@/lib/entityPaths";

import { useDerivedBullets } from "../hooks/useDerivedBullets";

interface EntryOverflowMenuProps {
  entryId: number;
  entryTitle: string;
  onEdit: () => void;
  onArchive: () => void;
}

/** Closed, open, or open with the archive confirmation showing. */
type MenuState = "closed" | "open" | "confirming-archive";

const ITEM_CLASS = "justify-start";
// Archive is destructive, so it reads crimson and keeps crimson on hover: the
// ghost variant's own hover is the action coral, the neighboring hue this control
// must never borrow.
const ARCHIVE_ITEM_CLASS =
  "justify-start text-destructive hover:bg-destructive-tint hover:text-destructive";

/**
 * The per-row overflow menu: edit, archive, and the bullets derived from this
 * entry. The derived bullets load lazily (only while the menu is open) and each
 * links into the Library, where the bullet is framed.
 *
 * The menu floats, so it carries the reserved elevation shadow. Archive is
 * confirm-gated and marked by both a trash icon and its label, because the
 * crimson sits one hue away from the action coral and must never be the only
 * signal that an action destroys something.
 */
export function EntryOverflowMenu({
  entryId,
  entryTitle,
  onEdit,
  onArchive,
}: EntryOverflowMenuProps) {
  const [menu, setMenu] = useState<MenuState>("closed");
  const [historyOpen, setHistoryOpen] = useState(false);
  const isOpen = menu !== "closed";
  const derived = useDerivedBullets(isOpen ? entryId : null);

  const archiveItemRef = useRef<HTMLButtonElement>(null);
  const confirmArchiveRef = useRef<HTMLButtonElement>(null);
  const previousMenu = useRef<MenuState>("closed");

  // Opening the gate unmounts the button the user just activated, and dismissing
  // it unmounts the dismiss button, so focus has to be carried across both swaps
  // by hand: this is a plain popup, not a Modal, and nothing else moves focus for
  // it. Opening the menu leaves focus on the trigger, which is why the dismiss
  // path checks where it came from before reclaiming focus.
  useEffect(() => {
    const cameFromGate = previousMenu.current === "confirming-archive";
    previousMenu.current = menu;
    if (menu === "confirming-archive") confirmArchiveRef.current?.focus();
    else if (menu === "open" && cameFromGate) archiveItemRef.current?.focus();
  }, [menu]);

  return (
    <div className="relative">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label={`Actions for ${entryTitle}`}
        aria-expanded={isOpen}
        onClick={() => setMenu(isOpen ? "closed" : "open")}
        className="text-muted-foreground size-8 shrink-0"
      >
        <MoreHorizontal aria-hidden />
      </Button>

      {isOpen && (
        <div className="bg-popover text-popover-foreground border-border shadow-floating absolute right-0 z-10 mt-1 flex w-64 flex-col gap-2 rounded-md border p-2">
          <div className="flex flex-col">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className={ITEM_CLASS}
              onClick={() => {
                setMenu("closed");
                onEdit();
              }}
            >
              Edit
            </Button>

            {menu === "confirming-archive" ? (
              <div
                role="group"
                aria-label="Archive this entry?"
                className="flex flex-col gap-2 px-3 py-2"
              >
                <p className="text-muted-foreground caption">Archive this entry?</p>
                <div className="flex items-center gap-2">
                  <Button
                    ref={confirmArchiveRef}
                    type="button"
                    variant="destructive"
                    size="sm"
                    onClick={() => {
                      setMenu("closed");
                      onArchive();
                    }}
                  >
                    <Trash2 aria-hidden />
                    Archive entry
                  </Button>
                  <Button type="button" variant="ghost" size="sm" onClick={() => setMenu("open")}>
                    Keep it
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                ref={archiveItemRef}
                type="button"
                variant="ghost"
                size="sm"
                className={ARCHIVE_ITEM_CLASS}
                onClick={() => setMenu("confirming-archive")}
              >
                <Trash2 aria-hidden />
                Archive
              </Button>
            )}

            <Button
              type="button"
              variant="ghost"
              size="sm"
              className={ITEM_CLASS}
              onClick={() => {
                setMenu("closed");
                setHistoryOpen(true);
              }}
            >
              History
            </Button>
          </div>

          <div className="border-border/60 border-t pt-2">
            <p className="text-muted-foreground caption px-3 pb-1">Derived bullets</p>
            {derived.status === "loading" && (
              <p className="text-muted-foreground caption px-3">Loading…</p>
            )}
            {derived.status === "error" && (
              <p className="text-destructive caption px-3">Could not load derived bullets.</p>
            )}
            {derived.status === "ready" && derived.bullets.length === 0 && (
              <p className="text-muted-foreground caption px-3">No bullets frame this entry yet.</p>
            )}
            {derived.bullets.length > 0 && (
              <ul className="flex flex-col">
                {derived.bullets.map((bullet) => (
                  <li key={bullet.id}>
                    <Link
                      to={libraryBulletHref(bullet.id)}
                      className="hover:bg-accent block truncate rounded-md px-3 py-1 text-sm"
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
