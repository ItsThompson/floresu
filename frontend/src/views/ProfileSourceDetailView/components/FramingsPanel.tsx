import { Plus } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";

import type { SourceFramings } from "../hooks/useSourceFramings";
import { FramingRow } from "./FramingRow";

interface FramingsPanelProps {
  framings: SourceFramings;
}

/**
 * Column two of the source detail: the bullet framings for this source, plus an
 * inline control to add a new one (a canonical bullet pre-linked to the source).
 * Generation happens in the user's agent over MCP, not here; this panel lists and
 * adds only.
 */
export function FramingsPanel({ framings }: FramingsPanelProps) {
  const [draft, setDraft] = useState("");
  const isAdding = framings.write.status === "saving";
  const addError = framings.write.status === "error" ? framings.write.message : null;

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!draft.trim()) return;
    framings.addFraming(draft);
    setDraft("");
  };

  return (
    <section aria-label="Bullet framings" className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold tracking-tight">Bullet framings</h2>

      {framings.status === "loading" && (
        <p className="text-muted-foreground text-sm">Loading framings…</p>
      )}
      {framings.status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          Could not load framings.
        </p>
      )}
      {framings.status === "ready" && framings.framings.length === 0 && (
        <p className="text-muted-foreground text-sm">No framings yet.</p>
      )}
      {framings.status === "ready" && framings.framings.length > 0 && (
        <ul className="flex flex-col gap-2">
          {framings.framings.map((framing) => (
            <FramingRow key={framing.id} framing={framing} />
          ))}
        </ul>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <textarea
          aria-label="New framing"
          placeholder="Add a bullet framing…"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          className="border-input bg-card text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 min-h-16 rounded-md border px-3 py-2 text-sm outline-none focus-visible:ring-[3px]"
        />
        {addError && (
          <p role="alert" className="text-destructive text-sm">
            {addError}
          </p>
        )}
        <Button
          type="submit"
          variant="outline"
          size="sm"
          disabled={isAdding || !draft.trim()}
          className="self-start"
        >
          <Plus className="size-3.5" /> {isAdding ? "Adding…" : "Add framing"}
        </Button>
      </form>
    </section>
  );
}
