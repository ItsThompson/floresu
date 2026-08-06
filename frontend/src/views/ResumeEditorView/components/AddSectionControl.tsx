import { useState } from "react";
import { Plus } from "lucide-react";

import { FIELD_SHAPE_CLASS } from "@/components/FormInputField";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { DEFAULT_SECTION_KIND, SECTION_KIND_OPTIONS, sectionKindLabel } from "../constants";
import type { SectionKind } from "../types";

interface AddSectionControlProps {
  /** Append a new section of the chosen kind and title to the resume document. */
  onAddSection: (kind: SectionKind, title: string) => void;
}

interface SectionDraft {
  kind: SectionKind;
  title: string;
}

/**
 * Adds the first (or any subsequent) section to a resume, so a web-only user can
 * build a resume from a blank starting point. It reveals a kind picker and title
 * field on activation; a blank title falls back to the kind's default label.
 */
export function AddSectionControl({ onAddSection }: AddSectionControlProps) {
  const [draft, setDraft] = useState<SectionDraft | null>(null);

  const submit = () => {
    if (!draft) return;
    const title = draft.title.trim() || sectionKindLabel(draft.kind);
    onAddSection(draft.kind, title);
    setDraft(null);
  };

  if (draft === null) {
    return (
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setDraft({ kind: DEFAULT_SECTION_KIND, title: "" })}
      >
        <Plus aria-hidden /> New section
      </Button>
    );
  }

  return (
    <div className="bg-card border-border flex flex-col gap-2 rounded-lg border p-3">
      <div className="flex gap-2">
        <select
          aria-label="Section kind"
          value={draft.kind}
          onChange={(event) => {
            const selected = SECTION_KIND_OPTIONS.find(
              (option) => option.kind === event.target.value,
            );
            if (selected) setDraft({ ...draft, kind: selected.kind });
          }}
          className={cn(FIELD_SHAPE_CLASS, "h-8 px-2")}
        >
          {SECTION_KIND_OPTIONS.map((option) => (
            <option key={option.kind} value={option.kind}>
              {option.label}
            </option>
          ))}
        </select>
        <input
          autoFocus
          aria-label="Section title"
          placeholder={sectionKindLabel(draft.kind)}
          value={draft.title}
          onChange={(event) => setDraft({ ...draft, title: event.target.value })}
          onKeyDown={(event) => event.key === "Enter" && submit()}
          className={cn(FIELD_SHAPE_CLASS, "h-8 flex-1 px-2")}
        />
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={submit}>
          Add section
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setDraft(null)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
