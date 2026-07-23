import { useState, type FormEvent } from "react";

import { FormInputField } from "@/components/FormInputField";
import { Button } from "@/components/ui/button";

import type { AddEntryFormValues, WorklogWrite } from "../types";

interface AddWorklogEntryFormProps {
  isAdding: boolean;
  error: string | null;
  onAdd: (entry: Omit<WorklogWrite, "source_ids">) => void;
  onCancel: () => void;
}

const INITIAL_VALUES: AddEntryFormValues = {
  title: "",
  entryDate: "",
  description: "",
  tags: "",
};

/**
 * The quick add-entry form in the contextual worklog panel. Title and date are
 * required; description and tags are optional. The panel pre-attaches the created
 * entry to the current source, so this form carries no source concern.
 */
export function AddWorklogEntryForm({ isAdding, error, onAdd, onCancel }: AddWorklogEntryFormProps) {
  const [values, setValues] = useState<AddEntryFormValues>(INITIAL_VALUES);
  const [missing, setMissing] = useState<Record<string, string>>({});

  const setField = (field: keyof AddEntryFormValues, value: string) =>
    setValues((prev) => ({ ...prev, [field]: value }));

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const errors: Record<string, string> = {};
    if (!values.title.trim()) errors.title = "This field is required.";
    if (!values.entryDate) errors.entry_date = "This field is required.";
    setMissing(errors);
    if (Object.keys(errors).length > 0) return;
    const description = values.description.trim();
    onAdd({
      title: values.title.trim(),
      entry_date: values.entryDate,
      description: description || null,
      tags: values.tags
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
        value={values.title}
        error={missing.title}
        onChange={(event) => setField("title", event.target.value)}
      />
      <FormInputField
        label="Date"
        name="entry_date"
        type="date"
        value={values.entryDate}
        error={missing.entry_date}
        onChange={(event) => setField("entryDate", event.target.value)}
      />
      <label className="flex flex-col gap-1.5">
        <span className="text-foreground text-sm font-medium">Description</span>
        <textarea
          name="description"
          value={values.description}
          onChange={(event) => setField("description", event.target.value)}
          className="border-input bg-background focus-visible:border-ring focus-visible:ring-ring/50 min-h-16 rounded-md border px-3 py-2 text-sm outline-none focus-visible:ring-[3px]"
        />
      </label>
      <FormInputField
        label="Tags"
        name="tags"
        placeholder="backend, payments"
        value={values.tags}
        onChange={(event) => setField("tags", event.target.value)}
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
