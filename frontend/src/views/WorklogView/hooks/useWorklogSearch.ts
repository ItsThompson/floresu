import { useCallback, useMemo, useState } from "react";

import { useSessionClient } from "@/api";
import { toSearchFilters } from "@/lib/searchFilters";

import { SEARCH_ERROR_MESSAGE } from "../constants";
import { toSearchFilterValues } from "../searchFilterValues";
import type {
  WorklogFilterValues,
  WorklogSearchActions,
  WorklogSearchState,
  WorklogSearchViewState,
} from "../types";

export interface UseWorklogSearchParams {
  /** The page's active filter bar, applied to the search as well as the timeline. */
  filters: WorklogFilterValues;
}

export interface UseWorklogSearch {
  state: WorklogSearchViewState;
  actions: WorklogSearchActions;
}

/**
 * Drives the embedded hybrid-search field. A submit posts the query and the
 * page's active filters to the single `/search` endpoint (the same deep module
 * the agent uses) and shows the fused ranked mix. An empty query returns nothing
 * rather than dumping the corpus, so it short-circuits before any request.
 * Ranking, fusion, and the lexical/semantic split all live on the backend. The
 * filter state is owned by the timeline hook and passed in, so one filter bar
 * narrows both surfaces.
 */
export function useWorklogSearch({ filters }: UseWorklogSearchParams): UseWorklogSearch {
  const client = useSessionClient();

  const [query, setQuery] = useState("");
  const [search, setSearch] = useState<WorklogSearchState>({ status: "idle" });

  const clear = useCallback(() => {
    setQuery("");
    setSearch({ status: "idle" });
  }, []);

  const submit = useCallback(async () => {
    const trimmed = query.trim();
    if (trimmed === "") {
      // An empty query returns nothing; never a full dump.
      setSearch({ status: "idle" });
      return;
    }

    // The `searching` arm carries no payload, so any prior results clear here
    // and a re-search never shows stale hits while the new ones resolve.
    setSearch({ status: "searching" });
    try {
      const { data, error } = await client.POST("/search", {
        body: { query: trimmed, filters: toSearchFilters(toSearchFilterValues(filters)) },
      });
      if (error || !data) throw new Error(SEARCH_ERROR_MESSAGE);
      setSearch({ status: "results", result: data });
    } catch {
      setSearch({ status: "error", message: SEARCH_ERROR_MESSAGE });
    }
  }, [client, query, filters]);

  const actions = useMemo<WorklogSearchActions>(
    () => ({ setQuery, submit, clear }),
    [submit, clear],
  );

  return {
    state: { query, search },
    actions,
  };
}
