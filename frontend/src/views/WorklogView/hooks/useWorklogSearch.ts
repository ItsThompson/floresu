import { useCallback, useMemo, useState } from "react";

import { useSessionClient } from "@/api";

import { SEARCH_ERROR_MESSAGE } from "../constants";
import type { ResolvedHit, SearchResult } from "../types";
import { resolveRankedHits } from "../utils";

type SearchNotice = NonNullable<SearchResult["notices"]>[number];
type SearchStatus = "idle" | "searching" | "error";

export interface WorklogSearchState {
  query: string;
  /** The flat ranked mix (worklog + bullets + directly-matching sources). */
  results: ResolvedHit[];
  /** Soft notices, e.g. semantic retrieval degraded to lexical-only. */
  notices: SearchNotice[];
  status: SearchStatus;
  /** True once a non-empty query has run, so the results region can show. */
  hasSearched: boolean;
}

export interface WorklogSearchActions {
  setQuery: (query: string) => void;
  submit: () => Promise<void>;
  clear: () => void;
}

export interface UseWorklogSearch {
  state: WorklogSearchState;
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
  const [results, setResults] = useState<ResolvedHit[]>([]);
  const [notices, setNotices] = useState<SearchNotice[]>([]);
  const [status, setStatus] = useState<SearchStatus>("idle");
  const [hasSearched, setHasSearched] = useState(false);

  const clear = useCallback(() => {
    setQuery("");
    setResults([]);
    setNotices([]);
    setStatus("idle");
    setHasSearched(false);
  }, []);

  const submit = useCallback(async () => {
    if (query.trim() === "") {
      // An empty query returns nothing; never a full dump.
      setResults([]);
      setNotices([]);
      setStatus("idle");
      setHasSearched(false);
      return;
    }

    setStatus("searching");
    setHasSearched(true);
    try {
      const { data, error } = await client.POST("/search", { body: { query } });
      if (error || !data) throw new Error(SEARCH_ERROR_MESSAGE);
      setResults(resolveRankedHits(data));
      setNotices(data.notices ?? []);
      setStatus("idle");
    } catch {
      setResults([]);
      setNotices([]);
      setStatus("error");
    }
  }, [client, query]);

  const actions = useMemo<WorklogSearchActions>(
    () => ({ setQuery, submit, clear }),
    [submit, clear],
  );

  return {
    state: { query, results, notices, status, hasSearched },
    actions,
  };
}
