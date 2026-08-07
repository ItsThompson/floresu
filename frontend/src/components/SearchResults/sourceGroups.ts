import type { components } from "@/api";

type SourceKind = components["schemas"]["SourceKind"];

/** The hit set rolled into the provenance graph: scored nodes plus their edges. */
export type SearchGraph = components["schemas"]["SearchGraph"];

/**
 * A source node from the search graph with its matched children attached, for
 * the grouped-by-source result view. `matchScore` is non-null only when the
 * source's own text matched the query directly.
 */
export interface SearchSourceGroup {
  id: number;
  label: string;
  kind: SourceKind;
  score: number;
  matchScore: number | null;
  worklog: SearchGraph["worklog"];
  bullets: SearchGraph["bullets"];
}

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
