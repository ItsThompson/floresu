import { Flag } from "lucide-react";

import type { BulletpointRecord } from "../types";

interface FramingRowProps {
  framing: BulletpointRecord;
}

/**
 * One bullet framing row: its text, a "used in N" count, and a shared marker when
 * the bullet is used by two or more resumes. The shared state shows both a flag
 * glyph and the count, so it never relies on color alone.
 */
export function FramingRow({ framing }: FramingRowProps) {
  const isShared = framing.used_in_count >= 2;
  return (
    <li className="border-border bg-card flex items-start gap-2 rounded-md border px-3 py-2">
      <p className="text-foreground flex-1 text-sm">{framing.text}</p>
      <span className="text-muted-foreground mono-meta inline-flex shrink-0 items-center gap-1">
        {isShared && <Flag aria-label="Shared across resumes" className="size-3.5" />}
        used in {framing.used_in_count}
      </span>
    </li>
  );
}
