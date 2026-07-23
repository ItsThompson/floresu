import { useMemo } from "react";

import { EMPTY_SEARCH_MESSAGE } from "../constants";
import type { SearchResultsProps } from "../types";
import { buildRankedRows, buildSearchGroups } from "../searchResults";
import { RankedHitList } from "./RankedHitList";
import { SearchSourceGroupCard } from "./SearchSourceGroupCard";

/**
 * The search result view: the flat ranked relevance list beside the same hits
 * grouped under their sources. Any soft notice (e.g. semantic retrieval degraded
 * to lexical-only) is surfaced above the results rather than failing the query.
 * Derives its view model from the result with pure `searchResults`.
 */
export function SearchResults({ result }: SearchResultsProps) {
  const rows = useMemo(() => buildRankedRows(result), [result]);
  const groups = useMemo(() => buildSearchGroups(result.graph), [result]);
  const notices = result.notices ?? [];

  if (rows.length === 0) {
    return <p className="text-muted-foreground text-sm">{EMPTY_SEARCH_MESSAGE}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      {notices.length > 0 && (
        <ul className="flex flex-col gap-1">
          {notices.map((notice) => (
            <li key={notice.code} role="status" className="text-muted-foreground text-xs">
              {notice.message}
            </li>
          ))}
        </ul>
      )}

      <section className="flex flex-col gap-2" aria-label="Top matches">
        <h2 className="text-sm font-semibold tracking-tight">Top matches</h2>
        <RankedHitList rows={rows} />
      </section>

      {groups.length > 0 && (
        <section className="flex flex-col gap-2" aria-label="Grouped by source">
          <h2 className="text-sm font-semibold tracking-tight">By source</h2>
          <div className="flex flex-col gap-3">
            {groups.map((group) => (
              <SearchSourceGroupCard key={group.id} group={group} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
