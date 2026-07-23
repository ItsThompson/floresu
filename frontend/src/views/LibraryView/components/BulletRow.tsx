import { Button } from "@/components/ui/button";

import type { BulletRowProps } from "../types";
import { isShared, usedInLabel } from "../bulletUsage";

/**
 * One canonical bullet: its statement text, a "used in N" usage badge, a shared
 * marker (flag glyph plus the word "Shared", so the meaning is never carried by
 * color alone) once two or more resumes reference it, and edit/archive actions.
 */
export function BulletRow({ bullet, onEdit, onArchive }: BulletRowProps) {
  const shared = isShared(bullet.used_in_count);

  return (
    <li className="border-border flex items-start justify-between gap-3 rounded-md border p-3">
      <div className="flex min-w-0 flex-col gap-1">
        <p className="text-sm">{bullet.text}</p>
        <div className="text-muted-foreground flex items-center gap-2 text-xs">
          <span>{usedInLabel(bullet.used_in_count)}</span>
          {shared && (
            <span className="text-primary inline-flex items-center gap-1 font-medium">
              <span aria-hidden="true">⚑</span> Shared
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
