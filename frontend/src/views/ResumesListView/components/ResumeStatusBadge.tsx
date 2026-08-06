import { Check, Lock } from "lucide-react";

import { cn } from "@/lib/utils";

import type { ResumeSummary } from "../types";

/** The lifecycle a badge announces, resolved from the resume's own columns. */
type BadgeState = "archived" | "finalized" | "living" | "draft";

const BADGE: Record<BadgeState, { label: string; className: string }> = {
  // An outline rather than a fill: an archived resume is out of the way, so it
  // recedes instead of competing with the active rows.
  archived: { label: "Archived", className: "border-border text-muted-foreground border" },
  // The olive tint carries "done and frozen". The label takes ink because olive
  // text on the olive tint measures 2.97:1, under the 4.5:1 floor for normal text.
  finalized: { label: "Finalized", className: "bg-success-tint text-foreground" },
  // `text-accent-foreground` is the deeper coral step: the `--primary` shade
  // clears only 4.00:1 on this tint, while this one measures 4.64:1.
  living: { label: "Living", className: "bg-accent text-accent-foreground" },
  draft: { label: "Draft", className: "bg-muted text-muted-foreground" },
};

/** Archived outranks everything; only an application resume can be finalized. */
function badgeState(resume: ResumeSummary): BadgeState {
  if (resume.archived_at !== null) return "archived";
  if (resume.status === "finalized") return "finalized";
  return resume.kind === "living" ? "living" : "draft";
}

interface ResumeStatusBadgeProps {
  resume: ResumeSummary;
}

/**
 * A resume's lifecycle badge. The state is derived rather than passed in, because
 * the row's own columns already say it: an archived resume is archived whatever
 * its status, and a living resume stays a draft for life (finalize is guarded to
 * application resumes).
 *
 * Every state renders its word, and finalized adds a check and a lock together,
 * so meaning never rests on color alone.
 */
export function ResumeStatusBadge({ resume }: ResumeStatusBadgeProps) {
  const state = badgeState(resume);
  const { label, className } = BADGE[state];
  return (
    <span
      className={cn(
        "caption inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5",
        className,
      )}
    >
      {state === "finalized" && (
        <>
          <Check aria-hidden className="size-3" />
          <Lock aria-hidden className="size-3" />
        </>
      )}
      {label}
    </span>
  );
}
