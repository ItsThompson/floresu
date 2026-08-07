import { Check, Circle } from "lucide-react";

import { cn } from "@/lib/utils";

import type { JobApplicationStatus } from "../types";

interface JobApplicationStatusBadgeProps {
  status: JobApplicationStatus;
}

/**
 * A job application's status badge, `added` or `submitted`. Each state pairs a
 * token tint with a glyph and the word together, so meaning never rests on color
 * alone (the accessibility rule).
 */
export function JobApplicationStatusBadge({ status }: JobApplicationStatusBadgeProps) {
  const isSubmitted = status === "submitted";
  return (
    <span
      className={cn(
        "caption inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5",
        isSubmitted ? "bg-success-tint text-foreground" : "bg-muted text-muted-foreground",
      )}
    >
      {isSubmitted ? (
        <>
          <Check aria-hidden className="size-3" />
          Submitted
        </>
      ) : (
        <>
          <Circle aria-hidden className="size-3" />
          Added
        </>
      )}
    </span>
  );
}
