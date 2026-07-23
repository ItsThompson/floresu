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
  const [title, setTitle] = useState(() => initialValues?.title ?? "");
  const [entryDate, setEntryDate] = useState(() => initialValues?.entryDate ?? "");
  const [description, setDescription] = useState(() => initialValues?.description ?? "");
  const [tags, setTags] = useState<string[]>(() => initialValues?.tags ?? []);
  const [sourceIds, setSourceIds] = useState<number[]>(() => initialValues?.sourceIds ?? []);
  const [tagDraft, setTagDraft] = useState("");
  const [showTitleError, setShowTitleError] = useState(false);
  const [showDateError, setShowDateError] = useState(false);

  const addTag = () => {
    const label = tagDraft.trim();
    if (label === "" || tags.includes(label)) {
      setTagDraft("");
      return;
    }
    setTags((prev) => [...prev, label]);
    setTagDraft("");
  };

  const toggleSource = (sourceId: number) => {
    setSourceIds((prev) =>
      prev.includes(sourceId) ? prev.filter((id) => id !== sourceId) : [...prev, sourceId],
    );
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const missingTitle = title.trim() === "";
    const missingDate = entryDate === "";
    setShowTitleError(missingTitle);
    setShowDateError(missingDate);
    if (missingTitle || missingDate) return;
    onSubmit({ title, entryDate, description, tags, sourceIds });
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
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          aria-invalid={showTitleError}
        />
        {showTitleError && <span className="text-destructive text-xs">{TITLE_REQUIRED_MESSAGE}</span>}
      </label>

      <label className="flex flex-col gap-1 text-sm font-medium">
        Date
        <input
          type="date"
          className={FIELD_CLASS}
          value={entryDate}
          onChange={(event) => setEntryDate(event.target.value)}
          aria-invalid={showDateError}
        />
        {showDateError && <span className="text-destructive text-xs">{DATE_REQUIRED_MESSAGE}</span>}
      </label>

      <label className="flex flex-col gap-1 text-sm font-medium">
        Description
        <textarea
          className={FIELD_CLASS}
          rows={3}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>

      <div className="flex flex-col gap-2 text-sm font-medium">
        Tags
        <div className="flex flex-wrap items-center gap-2">
          {tags.map((tag) => (
            <TagPill key={tag} label={tag} onRemove={() => setTags((prev) => prev.filter((existingTag) => existingTag !== tag))} />
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
                  checked={sourceIds.includes(source.id)}
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
