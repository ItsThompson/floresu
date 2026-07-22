import { useState } from "react";

import { Button } from "@/components/ui/button";

import type { IdentityVariantRead, ReplacementPrompt } from "../hooks/useIdentityVariants";

interface ReplacementPromptDialogProps {
  prompt: ReplacementPrompt;
  /** Active variants other than the one being archived, offered as replacements. */
  candidates: IdentityVariantRead[];
  onCancel: () => void;
  /** Records the chosen replacement; the resume re-point is wired in the resume editor. */
  onConfirm: (replacementId: number) => void;
}

/**
 * Shown when archiving a variant that a living resume references. It surfaces how
 * many resumes reference it and lets the user pick which variant those resumes
 * should use instead. Applying the re-point across the referencing resumes is the
 * resume editor's job; this dialog surfaces the prompt and the chosen replacement.
 */
export function ReplacementPromptDialog({
  prompt,
  candidates,
  onCancel,
  onConfirm,
}: ReplacementPromptDialogProps) {
  const [replacementId, setReplacementId] = useState<number | null>(candidates[0]?.id ?? null);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Pick a replacement variant"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <div className="bg-card border-border flex w-full max-w-md flex-col gap-4 rounded-xl border p-6">
        <h2 className="text-lg font-semibold tracking-tight">Pick a replacement variant</h2>
        <p className="text-muted-foreground text-sm">
          {prompt.resumeIds.length} living resume
          {prompt.resumeIds.length === 1 ? "" : "s"} reference this variant. Choose which variant
          they should use instead before archiving.
        </p>

        {candidates.length === 0 ? (
          <p role="alert" className="text-destructive text-sm">
            Create another variant first so referencing resumes have a replacement.
          </p>
        ) : (
          <label className="flex flex-col gap-1.5">
            <span className="text-foreground text-sm font-medium">Replacement</span>
            <select
              value={replacementId ?? undefined}
              onChange={(event) => setReplacementId(Number(event.target.value))}
              className="border-input bg-background h-9 rounded-md border px-3 text-sm outline-none"
            >
              {candidates.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.label}
                </option>
              ))}
            </select>
          </label>
        )}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={replacementId === null}
            onClick={() => replacementId !== null && onConfirm(replacementId)}
          >
            Continue
          </Button>
        </div>
      </div>
    </div>
  );
}
