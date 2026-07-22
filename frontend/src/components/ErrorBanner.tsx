import { X } from "lucide-react";

interface ErrorBannerProps {
  message: string;
  onDismiss: () => void;
}

/**
 * A dismissible inline error banner for non-fatal action failures (a failed
 * reorder, archive, or rename). Announced as an alert; the surrounding surface
 * stays usable so the user can retry.
 */
export function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className="border-destructive/40 text-destructive flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
    >
      <span>{message}</span>
      <button
        type="button"
        aria-label="Dismiss error"
        onClick={onDismiss}
        className="rounded p-0.5 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
      >
        <X className="size-4" />
      </button>
    </div>
  );
}
