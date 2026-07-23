import { useCallback, useEffect, useState } from "react";

import { useSessionClient } from "@/api";
import type { WriteState } from "@/lib/asyncState";
import { extractProblem } from "@/lib/problemDetail";

import type { BulletpointRecord, LoadStatus } from "../types";

export interface SourceFramings {
  status: LoadStatus;
  framings: BulletpointRecord[];
  write: WriteState;
  addFraming: (text: string) => void;
}

/**
 * The library bullets that frame one source. The list endpoint has no per-source
 * filter, so this loads active bullets and keeps those linked to the source
 * (P0 scale). Adding a framing here creates a canonical bullet pre-linked to the
 * source; full bullet editing lives in the Library.
 */
export function useSourceFramings(sourceId: number | null): SourceFramings {
  const client = useSessionClient();
  const [status, setStatus] = useState<LoadStatus>(sourceId === null ? "ready" : "loading");
  const [framings, setFramings] = useState<BulletpointRecord[]>([]);
  const [write, setWrite] = useState<WriteState>({ status: "idle" });

  useEffect(() => {
    if (sourceId === null) return;
    let active = true;
    setStatus("loading");
    void client
      .GET("/bullets")
      .then(({ data }) => {
        if (!active) return;
        if (!data) {
          setStatus("error");
          return;
        }
        setFramings(data.filter((bullet) => bullet.source_ids.includes(sourceId)));
        setStatus("ready");
      })
      .catch(() => {
        if (active) setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [client, sourceId]);

  const addFraming = useCallback(
    (text: string) => {
      if (sourceId === null || !text.trim()) return;
      setWrite({ status: "saving" });
      void client
        .POST("/bullets", { body: { text: text.trim(), source_ids: [sourceId] } })
        .then(({ data, error }) => {
          if (error || !data) {
            setWrite({ status: "error", message: extractProblem(error).message });
            return;
          }
          setWrite({ status: "idle" });
          setFramings((current) => [data, ...current]);
        })
        .catch(() => {
          setWrite({ status: "error", message: "Could not add that framing." });
        });
    },
    [client, sourceId],
  );

  return { status, framings, write, addFraming };
}
