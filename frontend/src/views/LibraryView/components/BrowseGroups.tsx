import { SOURCE_KIND_LABELS } from "@/lib/sourceKindLabels";

import type { BrowseGroupsProps } from "../types";
import { BulletRow } from "./BulletRow";

/**
 * Browse mode: bullets grouped under each source they link to, one section per
 * group. A bullet linked to several sources is rendered once under each. The
 * grouping itself is computed in `bulletGrouping.groupBulletsBySource`; this component
 * only lays the groups out.
 */
export function BrowseGroups({ groups, onEdit, onArchive }: BrowseGroupsProps) {
  return (
    <div className="flex flex-col gap-6">
      {groups.map((group) => (
        <section key={group.key} className="flex flex-col gap-1">
          <h2 className="caption text-muted-foreground flex items-center gap-2">
            {group.label}
            {group.kind && <span className="mono-tag">{SOURCE_KIND_LABELS[group.kind]}</span>}
          </h2>
          <ul className="divide-border/60 flex flex-col divide-y">
            {group.bullets.map((bullet) => (
              <BulletRow key={bullet.id} bullet={bullet} onEdit={onEdit} onArchive={onArchive} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
