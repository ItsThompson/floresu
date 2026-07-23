import { UNATTACHED_GROUP_KEY, UNATTACHED_GROUP_LABEL } from "./constants";
import type { Bullet, BulletGroup, Source } from "./types";

/**
 * Group bullets under each source they link to, ordered by the source sort order.
 * A bullet linked to several sources appears once under each. A bullet linked to
 * no currently-known source (empty edges, or only archived sources) falls into a
 * single trailing "unattached" group, so no bullet is ever dropped.
 */
export function groupBulletsBySource(bullets: Bullet[], sources: Source[]): BulletGroup[] {
  const knownSourceIds = new Set(sources.map((source) => source.id));
  const orderedSources = [...sources].sort((a, b) => a.sort_order - b.sort_order);

  const groups: BulletGroup[] = [];
  for (const source of orderedSources) {
    const groupBullets = bullets.filter((bullet) => bullet.source_ids.includes(source.id));
    if (groupBullets.length === 0) continue;
    groups.push({
      key: `source-${source.id}`,
      label: source.display_label,
      kind: source.kind,
      bullets: groupBullets,
    });
  }

  const unattached = bullets.filter((bullet) =>
    bullet.source_ids.every((id) => !knownSourceIds.has(id)),
  );
  if (unattached.length > 0) {
    groups.push({
      key: UNATTACHED_GROUP_KEY,
      label: UNATTACHED_GROUP_LABEL,
      kind: null,
      bullets: unattached,
    });
  }

  return groups;
}
