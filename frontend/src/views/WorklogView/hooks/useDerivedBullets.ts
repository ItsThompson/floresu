import { useMemo } from "react";
import useSWR from "swr";

import { useSessionClient } from "@/api";

import type { BulletpointRecord, DerivedBullet } from "../types";

type DerivedStatus = "idle" | "loading" | "ready" | "error";

export interface UseDerivedBullets {
  bullets: DerivedBullet[];
  status: DerivedStatus;
}

/**
 * Resolves the canonical bullets that frame one entry, lazily. The `/bullets`
 * read is enabled only once an entry is active (a row's overflow menu is open),
 * and swr shares the single fetch across every row. The entry-to-bullet edge is
 * the bullet's `worklog_ids`, so a bullet framing this entry is one whose edges
 * include it.
 */
export function useDerivedBullets(entryId: number | null): UseDerivedBullets {
  const client = useSessionClient();

  const { data, error } = useSWR<BulletpointRecord[]>(
    entryId === null ? null : "/bullets",
    async () => {
      const { data, error } = await client.GET("/bullets");
      if (error || !data) throw new Error("Could not load bullets.");
      return data;
    },
    { revalidateOnFocus: false, revalidateOnReconnect: false },
  );

  const bullets = useMemo<DerivedBullet[]>(() => {
    if (entryId === null || !data) return [];
    return data
      .filter((bullet) => bullet.worklog_ids.includes(entryId))
      .map((bullet) => ({ id: bullet.id, text: bullet.text }));
  }, [data, entryId]);

  const status: DerivedStatus =
    entryId === null ? "idle" : error ? "error" : data === undefined ? "loading" : "ready";

  return { bullets, status };
}
