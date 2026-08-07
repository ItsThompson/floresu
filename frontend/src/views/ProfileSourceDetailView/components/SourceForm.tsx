import { useState, type FormEvent } from "react";

import { FormInputField } from "@/components/FormInputField";
import { Button } from "@/components/ui/button";

import type { SourceFieldDesc } from "../sourceForm";
import type { SourceFormValues } from "../types";

interface SourceFormProps {
  fields: SourceFieldDesc[];
  initialValues: SourceFormValues;
  initialOngoing: boolean;
  isSaving: boolean;
  /** Field-level errors from the server, keyed by field name. */
  serverErrors: Record<string, string>;
  saveError: string | null;
  submitLabel: string;
  onSubmit: (values: SourceFormValues, ongoing: boolean) => void;
}

/**
 * The basic-info form (column one of the source detail). It renders the kind's
 * declared fields plus the common start/end dates and summary, holding its own
 * controlled state so a failed save never clears input. Required-field checks run
 * client-side; server field errors merge in by field name. It carries no kind
 * knowledge beyond the descriptors it is handed.
 */
export function SourceForm({
  fields,
  initialValues,
  initialOngoing,
  isSaving,
  serverErrors,
  saveError,
  submitLabel,
  onSubmit,
}: SourceFormProps) {
  const [values, setValues] = useState<SourceFormValues>(initialValues);
  const [ongoing, setOngoing] = useState(initialOngoing);
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  const setField = (name: string, value: string) =>
    setValues((current) => ({ ...current, [name]: value }));

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const missing = fields.reduce<Record<string, string>>((acc, field) => {
      if (field.required && !values[field.name]?.trim())
        acc[field.name] = "This field is required.";
      return acc;
    }, {});
    setLocalErrors(missing);
    if (Object.keys(missing).length === 0) onSubmit(values, ongoing);
  };

  const errorFor = (name: string) => localErrors[name] ?? serverErrors[name];

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4" aria-label="Basic information">
      <h2 className="text-sm font-semibold tracking-tight">Basic information</h2>

      {fields.map((field) =>
        field.type === "textarea" ? (
          <label key={field.name} className="flex flex-col gap-1.5">
            <span className="text-foreground caption">{field.label}</span>
            <textarea
              name={field.name}
              value={values[field.name] ?? ""}
              placeholder={field.placeholder}
              onChange={(event) => setField(field.name, event.target.value)}
              className="border-input bg-card text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 min-h-20 rounded-md border px-3 py-2 text-sm outline-none focus-visible:ring-[3px]"
            />
          </label>
        ) : (
          <FormInputField
            key={field.name}
            label={field.label}
            name={field.name}
            value={values[field.name] ?? ""}
            placeholder={field.placeholder}
            error={errorFor(field.name)}
            onChange={(event) => setField(field.name, event.target.value)}
          />
        ),
      )}

      <FormInputField
        label="Start date"
        name="date_start"
        type="date"
        value={values.date_start ?? ""}
        onChange={(event) => setField("date_start", event.target.value)}
      />

      <div className="flex flex-col gap-1.5">
        <label className="caption flex items-center gap-2">
          <input
            type="checkbox"
            checked={ongoing}
            onChange={(event) => setOngoing(event.target.checked)}
          />
          Ongoing (Present)
        </label>
        {!ongoing && (
          <FormInputField
            label="End date"
            name="date_end"
            type="date"
            value={values.date_end ?? ""}
            onChange={(event) => setField("date_end", event.target.value)}
          />
        )}
      </div>

      <label className="flex flex-col gap-1.5">
        <span className="text-foreground caption">Summary</span>
        <textarea
          name="summary"
          value={values.summary ?? ""}
          onChange={(event) => setField("summary", event.target.value)}
          className="border-input bg-card text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 min-h-24 rounded-md border px-3 py-2 text-sm outline-none focus-visible:ring-[3px]"
        />
      </label>

      {saveError && (
        <p role="alert" className="text-destructive text-sm">
          {saveError}
        </p>
      )}

      <Button type="submit" disabled={isSaving} className="self-start">
        {isSaving ? "Saving…" : submitLabel}
      </Button>
    </form>
  );
}
