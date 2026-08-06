import { useState } from "react";
import { TriangleAlert } from "lucide-react";

import { Modal } from "@/components/Modal";
import { Button } from "@/components/ui/button";

import type { ResumeEditScope, ScopePromptContext } from "../types";

interface ScopeDialogProps {
  /** The pending shared-bullet edit, or null when no prompt is active. */
  context: ScopePromptContext | null;
  onApply: (scope: ResumeEditScope) => void;
  onCancel: () => void;
}

/**
 * The copy-on-write scope prompt, shown only when the edited bullet is used in
 * two or more resumes (the backend returns the count and drives the prompt; the
 * view never computes scope). The default is "Only this resume" (a safe fork);
 * "Everywhere" is visibly marked higher-impact because it rewrites the canonical
 * bullet for every resume that references it.
 *
 * That mark is ochre rather than crimson: the edit is legitimate, it just reaches
 * past this resume. The tint carries the words "Higher impact" and the count it
 * would rewrite, so the option never states its consequence in color alone.
 */
export function ScopeDialog({ context, onApply, onCancel }: ScopeDialogProps) {
  const [scope, setScope] = useState<ResumeEditScope>("this_resume");

  // Reset the selection to the safe default each time a new prompt opens.
  const promptId = context?.bulletId ?? null;
  const [lastPromptId, setLastPromptId] = useState<number | null>(promptId);
  if (promptId !== lastPromptId) {
    setLastPromptId(promptId);
    setScope("this_resume");
  }

  if (!context) return null;

  return (
    <Modal
      isOpen
      onClose={onCancel}
      title={`This bullet is used in ${context.usedInCount} resumes`}
    >
      <p className="text-muted-foreground text-sm">Apply your edit:</p>

      <fieldset className="flex flex-col gap-2">
        <label className="flex items-start gap-2 rounded-md p-3 text-sm">
          <input
            type="radio"
            name="edit-scope"
            className="mt-1"
            checked={scope === "this_resume"}
            onChange={() => setScope("this_resume")}
          />
          <span>
            <span className="text-foreground font-medium">Only this resume</span>
            <span className="text-muted-foreground caption block">
              Forks a private copy; other resumes keep the original.
            </span>
          </span>
        </label>

        <label className="bg-warning-tint text-foreground flex items-start gap-2 rounded-md p-3 text-sm">
          <input
            type="radio"
            name="edit-scope"
            className="mt-1"
            checked={scope === "everywhere"}
            onChange={() => setScope("everywhere")}
          />
          <span>
            <span className="flex items-center gap-1.5 font-medium">
              Everywhere it&apos;s used
              <span className="caption inline-flex items-center gap-1">
                <TriangleAlert aria-hidden className="size-3.5" />
                Higher impact
              </span>
            </span>
            <span className="caption block">
              Rewrites the shared bullet for all {context.usedInCount} resumes.
            </span>
          </span>
        </label>
      </fieldset>

      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button onClick={() => onApply(scope)}>Apply</Button>
      </div>
    </Modal>
  );
}
