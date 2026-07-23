import type { RankedRow, SearchGraph, SearchResult, SearchSourceGroup } from "./types";

const byScoreDesc = (a: { score: number }, b: { score: number }): number => b.score - a.score;

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
