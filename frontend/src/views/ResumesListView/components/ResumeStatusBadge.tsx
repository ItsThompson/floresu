import { Check, Lock } from "lucide-react";

import type { components } from "@/api";
import { cn } from "@/lib/utils";

type ResumeStatus = components["schemas"]["ResumeStatus"];

interface ResumeStatusBadgeProps {
  status: ResumeStatus;
}

/**
 * A resume's lifecycle badge. A finalized resume reads as read-only through a
 * check, a lock icon, and the word "Finalized" together, so meaning never rests
 * on color alone (the accessibility rule).
 */
export function ResumeStatusBadge({ status }: ResumeStatusBadgeProps) {
  const isFinalized = status === "finalized";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
        isFinalized ? "bg-secondary text-secondary-foreground" : "text-muted-foreground",
      )}
    >
      {isFinalized ? (
        <>
          <Check aria-hidden className="size-3" />
          <Lock aria-hidden className="size-3" />
          Finalized
        </>
      ) : (
        "Draft"
      )}
    </span>
  );
}
