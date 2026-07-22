import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";

import type { BulletFormProps, BulletFormValues } from "../types";
import { toggleValue } from "../utils";
import { FilterCheckboxGroup } from "./FilterCheckboxGroup";

/**
 * The create/edit bullet form. It owns its controlled values seeded from
 * `initialValues`, so a failed save (the parent keeps the form open and passes
 * `error`) preserves everything the user typed. Submit is blocked until the
 * statement has text. Links to sources and/or worklog entries are the bullet's
 * provenance edges; the backend applies an edit everywhere the bullet is used.
 */
export function BulletForm({
  mode,
  initialValues,
  sources,
  worklogEntries,
  isSaving,
  error,
  onSubmit,
  onCancel,
}: BulletFormProps) {
  const [values, setValues] = useState<BulletFormValues>(initialValues);
  const canSubmit = values.text.trim().length > 0 && !isSaving;

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    onSubmit({ ...values, text: values.text.trim() });
  };

  return (
    <form
      onSubmit={handleSubmit}
      aria-label={mode === "edit" ? "Edit bullet" : "New bullet"}
      className="border-border flex flex-col gap-3 rounded-md border p-4"
    >
      <label className="flex flex-col gap-1.5 text-sm font-medium">
        Statement
        <textarea
          value={values.text}
          onChange={(event) => setValues((prev) => ({ ...prev, text: event.target.value }))}
          rows={3}
          className="border-input bg-background focus-visible:border-ring focus-visible:ring-ring/50 rounded-md border px-3 py-2 text-sm outline-none focus-visible:ring-[3px]"
        />
      </label>

      <FilterCheckboxGroup
        legend="Sources"
        options={sources.map((source) => ({ value: source.id, label: source.display_label }))}
        selected={values.sourceIds}
        onToggle={(id) =>
          setValues((prev) => ({ ...prev, sourceIds: toggleValue(prev.sourceIds, id) }))
        }
      />

      <FilterCheckboxGroup
        legend="Worklog entries"
        options={worklogEntries.map((entry) => ({
          value: entry.id,
          label: `${entry.title} (${entry.entry_date})`,
        }))}
        selected={values.worklogIds}
        onToggle={(id) =>
          setValues((prev) => ({ ...prev, worklogIds: toggleValue(prev.worklogIds, id) }))
        }
      />

      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      <div className="flex gap-2">
        <Button type="submit" disabled={!canSubmit}>
          {isSaving ? "Saving…" : "Save bullet"}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel} disabled={isSaving}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
