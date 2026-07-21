import { useState } from "react";
import { Library, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";

interface AddItemControlsProps {
  /** Open the library picker to reference an existing canonical bullet. */
  onPullFromLibrary: () => void;
  /** Create a net-new resume-local (non-searchable) inline item. */
  onAddInline: (text: string) => void;
}

/**
 * The per-section add controls: "pull from library" (references a canonical
 * bullet) and "new" (a resume-local inline bullet). The inline path reveals a
 * small text field so the item is created with content, avoiding an empty save.
 */
export function AddItemControls({ onPullFromLibrary, onAddInline }: AddItemControlsProps) {
  const [draft, setDraft] = useState<string | null>(null);

  const submit = () => {
    const text = (draft ?? "").trim();
    if (text) onAddInline(text);
    setDraft(null);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={onPullFromLibrary}>
          <Library aria-hidden /> pull from library
        </Button>
        <Button variant="outline" size="sm" onClick={() => setDraft("")}>
          <Plus aria-hidden /> new
        </Button>
      </div>

      {draft !== null && (
        <div className="flex gap-2">
          <input
            autoFocus
            aria-label="New bullet text"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && submit()}
            className="border-input bg-background h-8 flex-1 rounded-md border px-2 text-sm"
          />
          <Button size="sm" onClick={submit}>
            Add
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setDraft(null)}>
            Cancel
          </Button>
        </div>
      )}
    </div>
  );
}
