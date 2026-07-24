import { useCallback, useMemo, useState } from "react";

import { useSessionClient } from "@/api";

import { SEARCH_ERROR_MESSAGE } from "../constants";
import { resolveRankedHits } from "../searchHits";
import type {
  WorklogSearchActions,
  WorklogSearchState,
  WorklogSearchViewState,
} from "../types";

export interface UseWorklogSearch {
  state: WorklogSearchViewState;
  actions: WorklogSearchActions;
}

/**
 * Drives the embedded hybrid-search field. A submit posts the query to the
 * single `/search` endpoint (the same deep module the agent uses) and shows the
 * fused ranked mix. An empty query returns nothing rather than dumping the
 * corpus, so it short-circuits before any request. Ranking, fusion, and the
 * lexical/semantic split all live on the backend.
 */
export function useWorklogSearch(): UseWorklogSearch {
  const client = useSessionClient();

  const [query, setQuery] = useState("");
  const [search, setSearch] = useState<WorklogSearchState>({ status: "idle" });

  const clear = useCallback(() => {
    setQuery("");
    setSearch({ status: "idle" });
  }, []);

  const submit = useCallback(async () => {
    if (query.trim() === "") {
      // An empty query returns nothing; never a full dump.
      setSearch({ status: "idle" });
      return;
    }

    // The `searching` arm carries no payload, so any prior results clear here
    // and a re-search never shows stale hits while the new ones resolve.
    setSearch({ status: "searching" });
    try {
      const { data, error } = await client.POST("/search", { body: { query } });
      if (error || !data) throw new Error(SEARCH_ERROR_MESSAGE);
      setSearch({ status: "results", results: resolveRankedHits(data), notices: data.notices ?? [] });
    } catch {
      setSearch({ status: "error", message: SEARCH_ERROR_MESSAGE });
    }
  }, [client, query]);

  const actions = useMemo<WorklogSearchActions>(
    () => ({ setQuery, submit, clear }),
    [submit, clear],
  );

  return {
    state: { query, search },
    actions,
  };
}
