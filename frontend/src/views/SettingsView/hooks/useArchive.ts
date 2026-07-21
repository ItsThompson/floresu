import { useCallback, useEffect, useMemo, useState } from "react";

import { useSessionClient, type SessionClient } from "@/api";

import { isSameArchivedItem } from "../constants";
import type { ArchivedItem, ArchivedItemKey } from "../types";
import { deleteArchivedItem, loadArchivedItems, restoreArchivedItem } from "./archiveApi";

const LOAD_ERROR = "Couldn't load your archived items.";
const ACTION_ERROR = "That action didn't complete. Try again.";

/**
 * Archive & Trash state.
 *
 * `status`      the load lifecycle for the archived list.
 * `items`       the archived items across all three domains, once loaded.
 * `loadError`   set only in the `error` status.
 * `pending`     the item whose restore or delete is in flight (disables its row).
 * `actionError` a failed restore/delete, surfaced without discarding the list.
 */
export interface ArchiveState {
  status: "loading" | "ready" | "error";
  items: ArchivedItem[];
  loadError: string | null;
  pending: ArchivedItemKey | null;
  actionError: string | null;
}

export interface ArchiveActions {
  restore: (item: ArchivedItem) => void;
  permanentlyDelete: (item: ArchivedItem) => void;
}

interface UseArchive {
  state: ArchiveState;
  actions: ArchiveActions;
}

/**
 * Drives the Archive & Trash panel: loads archived worklog entries, sources, and
 * bullets, then restores or permanently deletes one on request. Both mutations
 * call the web-only lifecycle routes and, on success, drop the item from the
 * list; restore returns it to its active views and delete removes it for good.
 * The confirmation gate lives in the panel: this hook performs the action it is
 * told to.
 */
export function useArchive(): UseArchive {
  const client = useSessionClient();
  const [state, setState] = useState<ArchiveState>({
    status: "loading",
    items: [],
    loadError: null,
    pending: null,
    actionError: null,
  });

  useEffect(() => {
    let active = true;
    setState((prev) => ({ ...prev, status: "loading", loadError: null }));
    loadArchivedItems(client)
      .then((items) => {
        if (!active) return;
        setState((prev) => ({ ...prev, status: "ready", items, loadError: null }));
      })
      .catch(() => {
        if (!active) return;
        setState((prev) => ({ ...prev, status: "error", loadError: LOAD_ERROR }));
      });
    return () => {
      active = false;
    };
  }, [client]);

  const runAction = useCallback(
    (item: ArchivedItem, action: (client: SessionClient, item: ArchivedItem) => Promise<void>) => {
      setState((prev) => ({
        ...prev,
        pending: { entityType: item.entityType, id: item.id },
        actionError: null,
      }));
      action(client, item)
        .then(() => {
          setState((prev) => ({
            ...prev,
            pending: null,
            items: prev.items.filter((existing) => !isSameArchivedItem(item, existing)),
          }));
        })
        .catch(() => {
          setState((prev) => ({ ...prev, pending: null, actionError: ACTION_ERROR }));
        });
    },
    [client],
  );

  const actions = useMemo<ArchiveActions>(
    () => ({
      restore: (item) => runAction(item, restoreArchivedItem),
      permanentlyDelete: (item) => runAction(item, deleteArchivedItem),
    }),
    [runAction],
  );

  return { state, actions };
}
