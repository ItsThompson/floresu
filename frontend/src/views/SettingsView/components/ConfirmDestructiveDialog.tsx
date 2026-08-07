import { Trash2 } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";

interface ConfirmDestructiveDialogProps {
  title: string;
  description: string;
  confirmLabel: string;
  /** When set, the user must type this exact phrase to enable Confirm. */
  typePhrase?: string;
  /** When set, the user must check this acknowledgement to enable Confirm. */
  acknowledgeLabel?: string;
  isBusy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * A modal confirmation for an irreversible action. The destructive action is
 * gated three ways so it is never a single mis-click: it is confirm-gated (this
 * dialog), the Confirm control carries a `trash-2` icon and a label (meaning by
 * shape, not color alone), and it stays disabled until the caller's explicit
 * gate is satisfied, a typed phrase or a checked acknowledgement. Escape and
 * Cancel dismiss without acting.
 *
 * It keeps its own chrome rather than rendering through
 * `frontend/src/components/Modal/Modal.tsx` because it is an `alertdialog`, not a
 * `dialog`: the role tells assistive technology this interrupts to confirm a
 * consequence, and it carries `aria-describedby` so the consequence is announced
 * with the title. It matches that modal's surface exactly: the warm scrim, the one
 * reserved elevation, and the card fill.
 */
export function ConfirmDestructiveDialog({
  title,
  description,
  confirmLabel,
  typePhrase,
  acknowledgeLabel,
  isBusy = false,
  onConfirm,
  onCancel,
}: ConfirmDestructiveDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const [typed, setTyped] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Move focus into the dialog: the typed input when present, else Cancel.
    dialogRef.current?.querySelector<HTMLElement>("input, button")?.focus();
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onCancel]);

  const phraseSatisfied = !typePhrase || typed === typePhrase;
  const acknowledgeSatisfied = !acknowledgeLabel || acknowledged;
  const canConfirm = phraseSatisfied && acknowledgeSatisfied && !isBusy;

  return (
    <div className="bg-espresso/40 fixed inset-0 z-50 flex items-center justify-center p-4 motion-safe:animate-in motion-safe:fade-in">
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="bg-card text-card-foreground border-border shadow-floating flex w-full max-w-md flex-col gap-4 rounded-lg border p-6"
      >
        <h2 id={titleId} className="text-lg font-semibold tracking-tight">
          {title}
        </h2>
        <p id={descriptionId} className="text-muted-foreground text-sm">
          {description}
        </p>

        {typePhrase && (
          <label className="flex flex-col gap-1.5">
            <span className="caption text-muted-foreground">
              Type <span className="text-foreground font-medium">{typePhrase}</span> to confirm.
            </span>
            <input
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              aria-label="Confirmation phrase"
              autoComplete="off"
              className="border-input bg-card text-foreground focus-visible:border-ring focus-visible:ring-ring/50 h-9 rounded-md border px-3 text-sm outline-none focus-visible:ring-[3px]"
            />
          </label>
        )}

        {acknowledgeLabel && (
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
              className="mt-1"
            />
            <span>{acknowledgeLabel}</span>
          </label>
        )}

        <div className="flex items-center justify-end gap-3">
          <Button variant="ghost" onClick={onCancel} disabled={isBusy}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={!canConfirm}>
            <Trash2 aria-hidden />
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
