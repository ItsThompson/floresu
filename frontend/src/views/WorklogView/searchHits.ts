import { formatDayLabel } from "./dateFormat";
import type { ResolvedHit, SearchResult } from "./types";

/**
 * Join each flat ranked hit to its graph node so it carries a human label. A hit
 * with no matching node is dropped rather than rendered label-less. Order is
 * preserved, so the fused RRF ranking is what the UI shows.
 */
export function resolveRankedHits(result: SearchResult): ResolvedHit[] {
  const worklog = new Map(result.graph.worklog.map((node) => [node.id, node]));
  const bullets = new Map(result.graph.bullets.map((node) => [node.id, node]));
  const sources = new Map(result.graph.sources.map((node) => [node.id, node]));

  return result.ranked.flatMap<ResolvedHit>((hit) => {
    if (hit.type === "worklog") {
      const node = worklog.get(hit.id);
      if (!node) return [];
      return [{ ...hit, label: node.title, detail: formatDayLabel(node.date) }];
    }
    if (hit.type === "bullet") {
      const node = bullets.get(hit.id);
      if (!node) return [];
      return [{ ...hit, label: node.text, detail: null }];
    }
    const node = sources.get(hit.id);
    if (!node) return [];
    return [{ ...hit, label: node.label, detail: node.kind }];
  });
}
