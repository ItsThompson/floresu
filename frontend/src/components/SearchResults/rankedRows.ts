import type { components } from "@/api";
import { formatDayLabel } from "@/lib/dateFormat";
import { SOURCE_KIND_LABELS } from "@/lib/sourceKindLabels";

type EmbedItemKind = components["schemas"]["EmbedItemKind"];
type RankedHit = components["schemas"]["RankedHit"];

/** The hybrid-search response: the flat ranked list, the scored graph, notices. */
export type SearchResult = components["schemas"]["SearchResult"];

/**
 * The one further fact worth printing beside a hit's label. `dateTime` holds the
 * ISO day when the detail is a date, so a `<time>` still carries a
 * machine-readable value; it is null for a detail that is not a date.
 */
export interface RankedRowDetail {
  text: string;
  dateTime: string | null;
}

/** One row of the flat RRF-ranked list, resolved from the graph. */
export interface RankedRow {
  key: string;
  id: number;
  type: EmbedItemKind;
  label: string;
  detail: RankedRowDetail | null;
  score: number;
}

interface RowContent {
  label: string;
  detail: RankedRowDetail | null;
}

/**
 * Resolve the flat ranked list into display rows, labeling each hit from its
 * matching graph node and carrying its secondary detail: a worklog's date, a
 * source's kind. A bullet has no detail, since its statement is its own label. A
 * hit whose node is missing degrades to its id rather than dropping out of the
 * list, which is how a source-less worklog hit stays visible.
 */
export function buildRankedRows(result: SearchResult): RankedRow[] {
  const sources = new Map(result.graph.sources.map((source) => [source.id, source]));
  const entries = new Map(result.graph.worklog.map((entry) => [entry.id, entry]));
  const bullets = new Map(result.graph.bullets.map((bullet) => [bullet.id, bullet]));

  const contentFor = (hit: RankedHit): RowContent | null => {
    if (hit.type === "worklog") {
      const entry = entries.get(hit.id);
      if (!entry) return null;
      return {
        label: entry.title,
        detail: { text: formatDayLabel(entry.date), dateTime: entry.date },
      };
    }
    if (hit.type === "source") {
      const source = sources.get(hit.id);
      if (!source) return null;
      return {
        label: source.label,
        detail: { text: SOURCE_KIND_LABELS[source.kind], dateTime: null },
      };
    }
    const bullet = bullets.get(hit.id);
    if (!bullet) return null;
    return { label: bullet.text, detail: null };
  };

  return result.ranked.map((hit) => {
    const content = contentFor(hit) ?? { label: `#${hit.id}`, detail: null };
    return {
      key: `${hit.type}-${hit.id}`,
      id: hit.id,
      type: hit.type,
      label: content.label,
      detail: content.detail,
      score: hit.score,
    };
  });
}
