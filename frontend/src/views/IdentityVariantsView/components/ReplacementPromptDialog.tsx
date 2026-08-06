import { TriangleAlert } from "lucide-react";
import { useState } from "react";

import { Modal } from "@/components/Modal";
import { Button } from "@/components/ui/button";

import type { IdentityVariantRead, ReplacementPrompt } from "../hooks/useIdentityVariants";

interface ReplacementPromptDialogProps {
  prompt: ReplacementPrompt;
  /** Active variants other than the one being archived, offered as replacements. */
  candidates: IdentityVariantRead[];
  onCancel: () => void;
  /** Posts the chosen replacement; the backend re-points the referencing resumes and archives. */
  onConfirm: (replacementId: number) => void;
}

/**
 * Shown when archiving a variant that a living resume references. It surfaces how
 * many resumes reference it and lets the user pick which variant those resumes
 * should use instead. Confirming posts the choice; the backend re-points every
 * referencing resume to it and archives the original in one atomic operation.
 *
 * Rendered through the shared `Modal`, so it inherits the one reserved elevation,
 * the warm scrim, and Escape-to-dismiss. Confirming reaches past this variant into
 * other people's resumes, so the ochre hint states that consequence in words
 * before the control that causes it.
 */
export function ReplacementPromptDialog({
  prompt,
  candidates,
  onCancel,
  onConfirm,
}: ReplacementPromptDialogProps) {
  const [replacementId, setReplacementId] = useState<number | null>(candidates[0]?.id ?? null);

  return (
    <Modal isOpen onClose={onCancel} title="Pick a replacement variant">
      <p className="text-muted-foreground text-sm">
        {prompt.resumeIds.length} living resume
        {prompt.resumeIds.length === 1 ? "" : "s"} reference this variant. Choose which variant they
        should use instead before archiving.
      </p>

      {candidates.length === 0 ? (
        <p role="alert" className="text-destructive text-sm">
          Create another variant first so referencing resumes have a replacement.
        </p>
      ) : (
        <label className="flex flex-col gap-1.5">
          <span className="text-foreground caption">Replacement</span>
          <select
            value={replacementId ?? undefined}
            onChange={(event) => setReplacementId(Number(event.target.value))}
            className="border-input bg-card text-foreground focus-visible:border-ring focus-visible:ring-ring/50 h-9 rounded-md border px-3 text-sm outline-none focus-visible:ring-[3px]"
          >
            {candidates.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                {candidate.label}
              </option>
            ))}
          </select>
        </label>
      )}

      <p className="bg-warning-tint text-foreground caption flex items-start gap-2 rounded-md px-3 py-2">
        <TriangleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
        Confirming re-points every referencing resume to the replacement and archives this variant,
        both in one step.
      </p>

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
          Archive and re-point
        </Button>
      </div>
    </Modal>
  );
}
