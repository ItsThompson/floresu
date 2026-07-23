import { useState } from "react";

import { Button } from "@/components/ui/button";

import { DATE_REQUIRED_MESSAGE, TITLE_REQUIRED_MESSAGE } from "../constants";
import type { EntryFormValues, SourceSummary } from "../types";
import { TagPill } from "./TagPill";

interface WorklogEntryFormProps {
  mode: "create" | "edit";
  initialValues: EntryFormValues | null;
  sources: SourceSummary[];
  isSaving: boolean;
  error: string | null;
  onSubmit: (values: EntryFormValues) => void;
  onCancel: () => void;
}

const FIELD_CLASS = "border-input bg-background rounded-md border px-3 py-2 text-sm";

const INITIAL_VALUES: EntryFormValues = {
  title: "",
  entryDate: "",
  description: "",
  tags: [],
  sourceIds: [],
};

/**
 * The create/edit entry form. Title and date are required (guarded here before a
 * request); description, tags, and source attachment are optional, and zero, one,
 * or many sources may be attached. A failed save keeps the form mounted with its
 * input intact and shows the server error inline.
 */
export function WorklogEntryForm({
  mode,
  initialValues,
  sources,
  isSaving,
  error,
  onSubmit,
  onCancel,
}: WorklogEntryFormProps) {
  const [values, setValues] = useState<EntryFormValues>(() => initialValues ?? INITIAL_VALUES);
  const [tagDraft, setTagDraft] = useState("");
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  const addTag = () => {
    const label = tagDraft.trim();
    if (label === "" || values.tags.includes(label)) {
      setTagDraft("");
      return;
    }
    setValues((prev) => ({ ...prev, tags: [...prev.tags, label] }));
    setTagDraft("");
  };

  const toggleSource = (sourceId: number) => {
    setValues((prev) => ({
      ...prev,
      sourceIds: prev.sourceIds.includes(sourceId)
        ? prev.sourceIds.filter((id) => id !== sourceId)
        : [...prev.sourceIds, sourceId],
    }));
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const nextErrors: Record<string, string> = {};
    if (values.title.trim() === "") nextErrors.title = TITLE_REQUIRED_MESSAGE;
    if (values.entryDate === "") nextErrors.entryDate = DATE_REQUIRED_MESSAGE;
    setLocalErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    onSubmit(values);
  };

  return (
    <form
      onSubmit={handleSubmit}
      aria-label={mode === "edit" ? "Edit entry" : "Add entry"}
      className="bg-card flex flex-col gap-4 rounded-lg border p-4"
    >
      <h2 className="text-lg font-semibold">{mode === "edit" ? "Edit entry" : "Add entry"}</h2>

      <label className="flex flex-col gap-1 text-sm font-medium">
        Title
        <input
          className={FIELD_CLASS}
          value={values.title}
          onChange={(event) => setValues((prev) => ({ ...prev, title: event.target.value }))}
          aria-invalid={Boolean(localErrors.title)}
        />
        {localErrors.title && <span className="text-destructive text-xs">{localErrors.title}</span>}
      </label>

      <label className="flex flex-col gap-1 text-sm font-medium">
        Date
        <input
          type="date"
          className={FIELD_CLASS}
          value={values.entryDate}
          onChange={(event) => setValues((prev) => ({ ...prev, entryDate: event.target.value }))}
          aria-invalid={Boolean(localErrors.entryDate)}
        />
        {localErrors.entryDate && (
          <span className="text-destructive text-xs">{localErrors.entryDate}</span>
        )}
      </label>

      <label className="flex flex-col gap-1 text-sm font-medium">
        Description
        <textarea
          className={FIELD_CLASS}
          rows={3}
          value={values.description}
          onChange={(event) => setValues((prev) => ({ ...prev, description: event.target.value }))}
        />
      </label>

      <div className="flex flex-col gap-2 text-sm font-medium">
        Tags
        <div className="flex flex-wrap items-center gap-2">
          {values.tags.map((tag) => (
            <TagPill
              key={tag}
              label={tag}
              onRemove={() =>
                setValues((prev) => ({
                  ...prev,
                  tags: prev.tags.filter((existingTag) => existingTag !== tag),
                }))
              }
            />
          ))}
        </div>
        <div className="flex items-center gap-2">
          <input
            className={FIELD_CLASS}
            value={tagDraft}
            aria-label="Add a tag"
            placeholder="Add a tag and press Enter"
            onChange={(event) => setTagDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                addTag();
              }
            }}
          />
          <Button type="button" variant="outline" size="sm" onClick={addTag}>
            Add
          </Button>
        </div>
      </div>

      {sources.length > 0 && (
        <fieldset className="flex flex-col gap-2 text-sm font-medium">
          <legend>Attach sources</legend>
          <div className="flex flex-col gap-1">
            {sources.map((source) => (
              <label key={source.id} className="flex items-center gap-2 font-normal">
                <input
                  type="checkbox"
                  checked={values.sourceIds.includes(source.id)}
                  onChange={() => toggleSource(source.id)}
                />
                {source.display_label}
              </label>
            ))}
          </div>
        </fieldset>
      )}

      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      <div className="flex items-center gap-2">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? "Saving…" : "Save entry"}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
