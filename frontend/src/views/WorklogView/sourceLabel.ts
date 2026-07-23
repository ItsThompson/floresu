import type { SourceSummary } from "./types";

/** The display label for a source id, or a stable fallback if it is unknown. */
export function sourceLabel(sources: SourceSummary[], sourceId: number): string {
  return sources.find((source) => source.id === sourceId)?.display_label ?? `Source ${sourceId}`;
}
