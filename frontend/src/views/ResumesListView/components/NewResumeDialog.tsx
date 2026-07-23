import { useState } from "react";

import { FormInputField } from "@/components/FormInputField";
import { Modal } from "@/components/Modal";
import { Button } from "@/components/ui/button";

import type { ResumeCreateRequest, ResumeFormValues, ResumeSummary, SourceMode } from "../types";

const SOURCE_OPTIONS: { mode: SourceMode; label: string }[] = [
  { mode: "blank", label: "A blank resume" },
  { mode: "duplicate", label: "A copy of an existing resume" },
  { mode: "from_resume", label: "Seeded from an existing resume" },
];

const INITIAL_VALUES: ResumeFormValues = { title: "", mode: "blank", sourceId: null };

interface NewResumeDialogProps {
  isOpen: boolean;
  onClose: () => void;
  /** Existing living resumes offered as a seed for duplicate/from-resume. */
  livingResumes: ResumeSummary[];
  /** Create the resume; resolves to the new id, or null on failure. */
  onCreate: (request: ResumeCreateRequest) => Promise<number | null>;
  /** Called with the new id after a successful create (the view navigates to the editor). */
  onCreated: (id: number) => void;
}

/**
 * Create a living resume: blank, a faithful duplicate of an existing one, or
 * seeded from an existing one. Application resumes are created from the Job
 * Applications view (they must link to a job application), so this dialog is
 * living-only. `kind` sets the result; `source` seeds the content (the §05
 * creation contract). A failed create keeps the dialog open with an inline error.
 */
export function NewResumeDialog({
  isOpen,
  onClose,
  livingResumes,
  onCreate,
  onCreated,
}: NewResumeDialogProps) {
  const [values, setValues] = useState<ResumeFormValues>(INITIAL_VALUES);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const needsSource = values.mode !== "blank";
  const canSubmit = !isSubmitting && (!needsSource || values.sourceId !== null);

  const submit = async () => {
    setIsSubmitting(true);
    setError(null);
    const request = buildCreateRequest(values.mode, values.sourceId, values.title.trim());
    const id = await onCreate(request);
    setIsSubmitting(false);
    if (id === null) {
      setError("Could not create the resume. Please try again.");
      return;
    }
    onCreated(id);
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="New resume">
      <FormInputField
        label="Title"
        name="resume-title"
        placeholder="e.g. Backend Engineer"
        value={values.title}
        onChange={(event) => setValues((prev) => ({ ...prev, title: event.target.value }))}
      />

      <fieldset className="flex flex-col gap-2">
        <legend className="text-foreground mb-1 text-sm font-medium">Start from</legend>
        {SOURCE_OPTIONS.map((option) => (
          <label key={option.mode} className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="source-mode"
              checked={values.mode === option.mode}
              onChange={() => setValues((prev) => ({ ...prev, mode: option.mode }))}
            />
            {option.label}
          </label>
        ))}
      </fieldset>

      {needsSource && (
        <label className="flex flex-col gap-1.5">
          <span className="text-foreground text-sm font-medium">Source resume</span>
          <select
            className="border-input bg-background h-9 rounded-md border px-3 text-sm"
            value={values.sourceId ?? ""}
            onChange={(event) =>
              setValues((prev) => ({
                ...prev,
                sourceId: event.target.value ? Number(event.target.value) : null,
              }))
            }
          >
            <option value="">Select a resume…</option>
            {livingResumes.map((resume) => (
              <option key={resume.id} value={resume.id}>
                {resume.title}
              </option>
            ))}
          </select>
        </label>
      )}

      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={() => void submit()} disabled={!canSubmit}>
          Create
        </Button>
      </div>
    </Modal>
  );
}

function buildCreateRequest(mode: SourceMode, sourceId: number | null, title: string): ResumeCreateRequest {
  const base = { kind: "living" as const, title: title || null };
  if (mode === "duplicate" && sourceId !== null) {
    return { ...base, source: { mode: "duplicate", duplicate_id: sourceId } };
  }
  if (mode === "from_resume" && sourceId !== null) {
    return { ...base, source: { mode: "from_resume", from_resume_id: sourceId } };
  }
  return { ...base, source: { mode: "blank" } };
}
