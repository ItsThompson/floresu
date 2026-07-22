import { useEffect, useId, useRef, type ReactNode } from "react";

import { cn } from "@/lib/utils";

const SIZE_CLASS = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-3xl",
} as const;

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** The accessible dialog title, rendered as the heading and wired to `aria-labelledby`. */
  title: string;
  children: ReactNode;
  /** Constrains the panel width; defaults to `md`. */
  size?: keyof typeof SIZE_CLASS;
}

/**
 * A minimal, dependency-free accessible modal: a labelled `role="dialog"` panel
 * over a dimmed backdrop. Escape and a backdrop click both close it, focus moves
 * to the panel on open, and the fade respects `prefers-reduced-motion` via the
 * `motion-safe` variant. Shared by the resume views (scope prompt, delete
 * confirm, create, library picker, expanded preview).
 */
export function Modal({ isOpen, onClose, title, children, size = "md" }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    panelRef.current?.focus();
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 motion-safe:animate-in motion-safe:fade-in"
      onClick={onClose}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cn(
          "bg-card text-card-foreground flex w-full flex-col gap-4 rounded-lg border p-6 shadow-lg outline-none",
          SIZE_CLASS[size],
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id={titleId} className="text-lg font-semibold tracking-tight">
          {title}
        </h2>
        {children}
      </div>
    </div>
  );
}
