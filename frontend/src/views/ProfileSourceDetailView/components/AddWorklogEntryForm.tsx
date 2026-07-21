import { useState, type FormEvent } from "react";

import { FormInputField } from "@/components/FormInputField";
import { Button } from "@/components/ui/button";

import type { WorklogWrite } from "../types";

interface AddWorklogEntryFormProps {
  isAdding: boolean;
  error: string | null;
  onAdd: (entry: Omit<WorklogWrite, "source_ids">) => void;
  onCancel: () => void;
}

/**
 * The quick add-entry form in the contextual worklog panel. Title and date are
 * required; description and tags are optional. The panel pre-attaches the created
 * entry to the current source, so this form carries no source concern.
 */
export function AddWorklogEntryForm({ isAdding, error, onAdd, onCancel }: AddWorklogEntryFormProps) {
  const [title, setTitle] = useState("");
  const [entryDate, setEntryDate] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [missing, setMissing] = useState<{ title?: string; entry_date?: string }>({});

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const errors: { title?: string; entry_date?: string } = {};
    if (!title.trim()) errors.title = "This field is required.";
    if (!entryDate) errors.entry_date = "This field is required.";
    setMissing(errors);
    if (Object.keys(errors).length > 0) return;
    onAdd({
      title: title.trim(),
      entry_date: entryDate,
      description: description.trim() ? description.trim() : null,
      tags: tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    });
  };

  return (
    <form onSubmit={handleSubmit} aria-label="Add worklog entry" className="flex flex-col gap-3">
      <FormInputField
        label="Title"
        name="title"
        value={title}
        error={missing.title}
        onChange={(event) => setTitle(event.target.value)}
      />
      <FormInputField
        label="Date"
        name="entry_date"
        type="date"
        value={entryDate}
        error={missing.entry_date}
        onChange={(event) => setEntryDate(event.target.value)}
      />
      <label className="flex flex-col gap-1.5">
        <span className="text-foreground text-sm font-medium">Description</span>
        <textarea
          name="description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          className="border-input bg-background focus-visible:border-ring focus-visible:ring-ring/50 min-h-16 rounded-md border px-3 py-2 text-sm outline-none focus-visible:ring-[3px]"
        />
      </label>
      <FormInputField
        label="Tags"
        name="tags"
        placeholder="backend, payments"
        value={tags}
        onChange={(event) => setTags(event.target.value)}
      />
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={isAdding}>
          {isAdding ? "Adding…" : "Add entry"}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel} disabled={isAdding}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
