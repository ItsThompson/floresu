import { useState } from "react";

import { Modal } from "@/components/Modal";
import { Button } from "@/components/ui/button";

import type { BulletpointRecord } from "../types";

interface LibraryPickerDialogProps {
  isOpen: boolean;
  onClose: () => void;
  /** Canonical bullets available to reference (archived ones are filtered out). */
  bullets: BulletpointRecord[];
  /** Add the chosen bullet to the current section as a library reference. */
  onSelect: (bulletId: number) => void;
}

/**
 * Pick a canonical bullet to reference from the current section. Adding one
 * inserts a `library_ref` item (the backend increments the bullet's "used in N").
 * A text filter narrows the list; the usage count is shown so shared bullets are
 * recognizable before they are added.
 */
export function LibraryPickerDialog({ isOpen, onClose, bullets, onSelect }: LibraryPickerDialogProps) {
  const [query, setQuery] = useState("");

  const available = bullets.filter((bullet) => bullet.archived_at === null);
  const matches = query
    ? available.filter((bullet) => bullet.text.toLowerCase().includes(query.toLowerCase()))
    : available;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Pull from library" size="lg">
      <input
        type="search"
        aria-label="Filter library bullets"
        placeholder="Filter bullets…"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        className="border-input bg-background h-9 rounded-md border px-3 text-sm"
      />

      {matches.length === 0 ? (
        <p className="text-muted-foreground text-sm">No matching library bullets.</p>
      ) : (
        <ul className="flex max-h-80 flex-col gap-2 overflow-auto">
          {matches.map((bullet) => (
            <li key={bullet.id}>
              <button
                type="button"
                onClick={() => onSelect(bullet.id)}
                className="hover:bg-accent flex w-full flex-col items-start gap-0.5 rounded-md border px-3 py-2 text-left text-sm"
              >
                <span>{bullet.text}</span>
                <span className="text-muted-foreground text-xs">
                  Used in {bullet.used_in_count} {bullet.used_in_count === 1 ? "resume" : "resumes"}
                </span>
              </button>
            </li>
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
