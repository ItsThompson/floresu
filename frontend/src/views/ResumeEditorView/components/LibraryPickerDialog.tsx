import { useState } from "react";

import { FIELD_SHAPE_CLASS } from "@/components/FormInputField";
import { Modal } from "@/components/Modal";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

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
export function LibraryPickerDialog({
  isOpen,
  onClose,
  bullets,
  onSelect,
}: LibraryPickerDialogProps) {
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
        className={cn(FIELD_SHAPE_CLASS, "h-9 px-3")}
      />

      {matches.length === 0 ? (
        <p className="text-muted-foreground text-sm">No matching library bullets.</p>
      ) : (
        <ul className="divide-border/60 flex max-h-80 flex-col divide-y overflow-auto">
          {matches.map((bullet) => (
            <li key={bullet.id}>
              <button
                type="button"
                onClick={() => onSelect(bullet.id)}
                className="hover:bg-muted flex w-full flex-col items-start gap-0.5 rounded-md px-2 py-2.5 text-left text-sm"
              >
                <span className="text-foreground">{bullet.text}</span>
                <span className="text-muted-foreground mono-meta">
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
