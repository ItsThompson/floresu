import { Plus } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";

interface AddSkillFormProps {
  onAdd: (name: string) => void;
}

/**
 * Adds a curated skill. A skill enters the list only through this explicit
 * action, never by auto-promotion from a tag, so curation stays deliberate.
 */
export function AddSkillForm({ onAdd }: AddSkillFormProps) {
  const [name, setName] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    onAdd(trimmed);
    setName("");
  };

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2">
      <input
        aria-label="New skill"
        placeholder="Add a skill…"
        value={name}
        onChange={(event) => setName(event.target.value)}
        className="border-input bg-background focus-visible:border-ring focus-visible:ring-ring/50 h-9 flex-1 rounded-md border px-3 text-sm outline-none focus-visible:ring-[3px]"
      />
      <Button type="submit" size="sm" disabled={!name.trim()}>
        <Plus className="size-3.5" /> Add
      </Button>
    </form>
  );
}
