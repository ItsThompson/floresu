import { Flag } from "lucide-react";

import { Button } from "@/components/ui/button";

import type { BulletRowProps } from "../types";
import { isShared, usedInLabel } from "../bulletUsage";

/**
 * One canonical bullet: its statement text, a "used in N" usage count, a shared
 * marker (a flag icon plus the word "Shared", so the meaning is never carried by
 * color alone) once two or more resumes reference it, and edit/archive actions.
 */
export function BulletRow({ bullet, onEdit, onArchive }: BulletRowProps) {
  const shared = isShared(bullet.used_in_count);

  return (
    <li className="flex items-start justify-between gap-3 py-2.5">
      <div className="flex min-w-0 flex-col gap-1">
        <p className="text-foreground text-sm">{bullet.text}</p>
        <div className="text-muted-foreground mono-meta flex items-center gap-2">
          <span>{usedInLabel(bullet.used_in_count)}</span>
          {shared && (
            <span className="inline-flex items-center gap-1">
              <Flag aria-hidden className="size-3.5" /> Shared
            </span>
          )}
        </div>
      </div>
      <div className="flex shrink-0 gap-1.5">
        <Button type="button" variant="ghost" size="sm" onClick={() => onEdit(bullet)}>
          Edit
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => onArchive(bullet.id)}>
          Archive
        </Button>
      </div>
    </li>
  );
}
