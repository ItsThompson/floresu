import { SOURCE_KIND_LABELS } from "../constants";
import type { BrowseGroupsProps } from "../types";
import { BulletRow } from "./BulletRow";

/**
 * Browse mode: bullets grouped under each source they link to, one section per
 * group. A bullet linked to several sources is rendered once under each. The
 * grouping itself is computed in `utils.groupBulletsBySource`; this component
 * only lays the groups out.
 */
export function BrowseGroups({ groups, onEdit, onArchive }: BrowseGroupsProps) {
  return (
    <div className="flex flex-col gap-6">
      {groups.map((group) => (
        <section key={group.key} className="flex flex-col gap-2">
          <h2 className="text-foreground flex items-center gap-2 text-sm font-semibold tracking-tight">
            {group.label}
            {group.kind && (
              <span className="text-muted-foreground text-xs font-normal">
                {SOURCE_KIND_LABELS[group.kind]}
              </span>
            )}
          </h2>
          <ul className="flex flex-col gap-2">
            {group.bullets.map((bullet) => (
              <BulletRow key={bullet.id} bullet={bullet} onEdit={onEdit} onArchive={onArchive} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
