import { useEffect, useState } from "react";

import { useSessionClient } from "@/api";
import type { components } from "@/api";

export type AuditEntry = components["schemas"]["AuditEntry"];

/**
 * The item-history fetch lifecycle. `ready` carries the rows (an empty array is
 * the empty state, not an error). `error` carries no rows, so a failed fetch never
 * shows stale content.
 */
export type ItemHistoryState =
  | { status: "loading" }
  | { status: "ready"; entries: AuditEntry[] }
  | { status: "error" };

/**
 * Load one item's audit trail (newest-first) from the session-authed
 * `GET /feed/history/{entity_type}/{entity_id}` route, only while `isOpen`. Each
 * open re-fetches from the loading state, so re-opening never shows a prior item's
 * rows, and an in-flight fetch that outlives the open is discarded.
 */
export function useItemHistory(
  entityType: string,
  entityId: number,
  isOpen: boolean,
): ItemHistoryState {
  const client = useSessionClient();
  const [state, setState] = useState<ItemHistoryState>({ status: "loading" });

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setState({ status: "loading" });
    client
      .GET("/feed/history/{entity_type}/{entity_id}", {
        params: { path: { entity_type: entityType, entity_id: entityId } },
      })
      .then(({ data, error }) => {
        if (cancelled) return;
        setState(error || !data ? { status: "error" } : { status: "ready", entries: data });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, entityType, entityId, client]);

  return state;
}
