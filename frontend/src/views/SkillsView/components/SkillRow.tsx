import { Archive, Check, GripVertical, Pencil, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import type { DragHandleProps } from "@/lib/reorder";

import type { SkillRead } from "../hooks/useSkills";

interface SkillRowProps {
  skill: SkillRead;
  handleProps: DragHandleProps;
  isDragging: boolean;
  onRename: (id: number, name: string) => void;
  onArchive: (id: number) => void;
}

/**
 * One skill row: a drag handle, the skill name with inline rename, its derived
 * usage count, and an archive control. The row is a flat drag source and drop
 * target so skills reorder by dragging one onto another.
 */
export function SkillRow({ skill, handleProps, isDragging, onRename, onArchive }: SkillRowProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(skill.name);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = draft.trim();
    if (trimmed && trimmed !== skill.name) onRename(skill.id, trimmed);
    setEditing(false);
  };

  return (
    <li
      {...handleProps}
      className={`group hover:bg-muted flex items-center gap-2 px-1.5 py-2 ${
        isDragging ? "opacity-50" : ""
      }`}
    >
      <GripVertical aria-hidden className="text-muted-foreground size-3.5 shrink-0 cursor-grab" />

      {editing ? (
        <form onSubmit={submit} className="flex flex-1 items-center gap-1">
          <input
            aria-label={`Rename ${skill.name}`}
            value={draft}
            autoFocus
            onChange={(event) => setDraft(event.target.value)}
            className="border-input bg-card text-foreground focus-visible:border-ring focus-visible:ring-ring/50 h-8 flex-1 rounded-md border px-2 text-sm outline-none focus-visible:ring-[3px]"
          />
          <button
            type="submit"
            aria-label="Save name"
            className="text-muted-foreground hover:text-foreground p-1"
          >
            <Check className="size-3.5" />
          </button>
          <button
            type="button"
            aria-label="Cancel rename"
            onClick={() => {
              setDraft(skill.name);
              setEditing(false);
            }}
            className="text-muted-foreground hover:text-foreground p-1"
          >
            <X className="size-3.5" />
          </button>
        </form>
      ) : (
        <>
          <span className="flex-1 truncate text-sm font-medium">{skill.name}</span>
          <span className="mono-meta text-muted-foreground shrink-0">
            used in {skill.usage_count}
          </span>
          <button
            type="button"
            aria-label={`Rename ${skill.name}`}
            onClick={() => setEditing(true)}
            className="text-muted-foreground hover:text-foreground rounded p-1 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
          >
            <Pencil className="size-3.5" />
          </button>
          <button
            type="button"
            aria-label={`Archive ${skill.name}`}
            onClick={() => onArchive(skill.id)}
            className="text-muted-foreground hover:text-destructive rounded p-1 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
          >
            <Archive className="size-3.5" />
          </button>
        </>
      )}
    </li>
  );
}
