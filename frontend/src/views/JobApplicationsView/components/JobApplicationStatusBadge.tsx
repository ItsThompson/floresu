import { Check, Circle } from "lucide-react";

import { cn } from "@/lib/utils";

import type { JobApplicationStatus } from "../types";

interface JobApplicationStatusBadgeProps {
  status: JobApplicationStatus;
}

/**
 * A job application's status badge. `submitted` reads through a check icon and
 * the word together, so meaning never rests on color alone (the accessibility
 * rule). P0 tracks only `added` and `submitted`.
 */
export function JobApplicationStatusBadge({ status }: JobApplicationStatusBadgeProps) {
  const isSubmitted = status === "submitted";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
        isSubmitted ? "bg-secondary text-secondary-foreground" : "text-muted-foreground",
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
