import { UNATTACHED_GROUP_KEY, UNATTACHED_GROUP_LABEL } from "./constants";
import type {
  Bullet,
  BulletGroup,
  LibraryFilters,
  RankedRow,
  SearchGraph,
  SearchQueryFilters,
  SearchResult,
  SearchSourceGroup,
  Source,
} from "./types";

/** The usage badge text: "Unused" at zero, otherwise "Used in N". */
export function usedInLabel(count: number): string {
  return count === 0 ? "Unused" : `Used in ${count}`;
}

/** A bullet is shared (shows the ⚑ marker) once two or more resumes reference it. */
export function isShared(count: number): boolean {
  return count >= 2;
}

const byScoreDesc = (a: { score: number }, b: { score: number }): number => b.score - a.score;

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

/**
 * Roll the search graph into per-source groups ordered by source score. Each
 * group carries the matched worklog entries attached to that source and the
 * matched bullets reachable from it, either linked to it directly or through one
 * of those worklog entries. Hits with no source are absent here by design; they
 * remain in the flat ranked list.
 */
export function buildSearchGroups(graph: SearchGraph): SearchSourceGroup[] {
  return [...graph.sources].sort(byScoreDesc).map((source) => {
    const worklog = graph.worklog
      .filter((entry) => entry.source_ids.includes(source.id))
      .sort(byScoreDesc);
    const worklogIds = new Set(worklog.map((entry) => entry.id));
    const bullets = graph.bullets
      .filter(
        (bullet) =>
          bullet.source_ids.includes(source.id) ||
          bullet.worklog_ids.some((id) => worklogIds.has(id)),
      )
      .sort(byScoreDesc);
    return {
      id: source.id,
      label: source.label,
      kind: source.kind,
      score: source.score,
      matchScore: source.match_score ?? null,
      worklog,
      bullets,
    };
  });
}

/**
 * Resolve the flat ranked list into display rows, labeling each hit from its
 * matching graph node. A hit whose node is missing degrades to its id rather
 * than dropping out of the list.
 */
export function buildRankedRows(result: SearchResult): RankedRow[] {
  const sourceLabels = new Map(result.graph.sources.map((source) => [source.id, source.label]));
  const worklogTitles = new Map(result.graph.worklog.map((entry) => [entry.id, entry.title]));
  const bulletTexts = new Map(result.graph.bullets.map((bullet) => [bullet.id, bullet.text]));

  return result.ranked.map((hit) => {
    const label =
      hit.type === "source"
        ? sourceLabels.get(hit.id)
        : hit.type === "worklog"
          ? worklogTitles.get(hit.id)
          : bulletTexts.get(hit.id);
    return {
      key: `${hit.type}-${hit.id}`,
      type: hit.type,
      label: label ?? `#${hit.id}`,
      score: hit.score,
    };
  });
}

/**
 * Map the local filter UI state onto the API filter body. `layer` is always
 * sent; the id/tag lists and the date range are included only when set, so an
 * unused filter never narrows the corpus.
 */
export function toSearchFilters(filters: LibraryFilters): SearchQueryFilters {
  const result: SearchQueryFilters = { layer: filters.layer };
  if (filters.sourceIds.length > 0) result.source_ids = filters.sourceIds;
  if (filters.kinds.length > 0) result.kinds = filters.kinds;
  if (filters.tags.length > 0) result.tags = filters.tags;
  if (filters.dateFrom || filters.dateTo) {
    result.date_range = { from: filters.dateFrom || null, to: filters.dateTo || null };
  }
  return result;
}

/** Toggle a value's membership in a selection list (immutably). */
export function toggleValue<T>(values: readonly T[], value: T): T[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}
