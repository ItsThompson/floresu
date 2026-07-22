import { useCallback, useEffect, useMemo, useState } from "react";

import { useSessionClient } from "@/api";
import { monthKey, monthKeyLabel } from "@/lib/formatDate";
import { extractProblem } from "@/lib/problemDetail";

import type { LoadStatus, WorklogSummary, WorklogWrite } from "../types";

export interface WorklogMonth {
  key: string;
  label: string;
  entries: WorklogSummary[];
}

export interface ContextualWorklog {
  status: LoadStatus;
  months: WorklogMonth[];
  entryCount: number;
  isAdding: boolean;
  addError: string | null;
  addEntry: (entry: Omit<WorklogWrite, "source_ids">) => void;
}

/**
 * One source's contextual worklog: the entries attached to it, grouped by month
 * newest-first. The list endpoint has no per-source filter, so this loads active
 * entries and keeps those linked to the source. Adding an entry here pre-attaches
 * it to the source, so the raw record and the framing view stay in step.
 */
export function useContextualWorklog(sourceId: number | null): ContextualWorklog {
  const client = useSessionClient();
  const [status, setStatus] = useState<LoadStatus>(sourceId === null ? "ready" : "loading");
  const [entries, setEntries] = useState<WorklogSummary[]>([]);
  const [isAdding, setIsAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  useEffect(() => {
    if (sourceId === null) return;
    let active = true;
    setStatus("loading");
    void client
      .GET("/worklog")
      .then(({ data }) => {
        if (!active) return;
        if (!data) {
          setStatus("error");
          return;
        }
        setEntries(data.filter((entry) => entry.source_ids.includes(sourceId)));
        setStatus("ready");
      })
      .catch(() => {
        if (active) setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [client, sourceId]);

  const months = useMemo(() => groupByMonth(entries), [entries]);

  const addEntry = useCallback(
    (entry: Omit<WorklogWrite, "source_ids">) => {
      if (sourceId === null) return;
      setIsAdding(true);
      setAddError(null);
      void client
        .POST("/worklog", { body: { ...entry, source_ids: [sourceId] } })
        .then(({ data, error }) => {
          setIsAdding(false);
          if (error || !data) {
            setAddError(extractProblem(error).message);
            return;
          }
          // The record carries the same fields as a summary row plus provenance;
          // keep only the summary shape for the timeline.
          setEntries((current) => [toSummary(data, sourceId), ...current]);
        })
        .catch(() => {
          setIsAdding(false);
          setAddError("Could not add that entry.");
        });
    },
    [client, sourceId],
  );

  return { status, months, entryCount: entries.length, isAdding, addError, addEntry };
}

/** Group entries into month buckets, newest month first and newest entry first. */
function groupByMonth(entries: WorklogSummary[]): WorklogMonth[] {
  const buckets = new Map<string, WorklogSummary[]>();
  for (const entry of entries) {
    const key = monthKey(entry.entry_date);
    const bucket = buckets.get(key);
    if (bucket) bucket.push(entry);
    else buckets.set(key, [entry]);
  }
  return [...buckets.entries()]
    .sort(([left], [right]) => right.localeCompare(left))
    .map(([key, monthEntries]) => ({
      key,
      label: monthKeyLabel(key),
      entries: monthEntries.sort((left, right) => right.entry_date.localeCompare(left.entry_date)),
    }));
}

/** Project a created worklog record onto the summary fields the timeline renders. */
function toSummary(
  record: {
    id: number;
    title: string;
    entry_date: string;
    description: string | null;
    tags: string[];
    source_ids: number[];
    archived_at: string | null;
  },
  sourceId: number,
): WorklogSummary {
  return {
    id: record.id,
    title: record.title,
    entry_date: record.entry_date,
    description: record.description,
    tags: record.tags,
    source_ids: record.source_ids.length ? record.source_ids : [sourceId],
    archived_at: record.archived_at,
  };
}
