import { useCallback, useEffect, useState } from "react";

import { useSessionClient } from "@/api";
import { extractProblem } from "@/lib/problemDetail";

import type {
  HubData,
  HubStatus,
  ProfileHubActions,
  ProfileHubState,
  SourceKind,
  SourceSummary,
} from "../types";

const EMPTY_DATA: HubData = { sources: [], skills: [], variants: [] };

/**
 * Loads the profile hub's three data surfaces (sources, skills, identity
 * variants) in parallel and owns the two hub-level source mutations: reordering a
 * kind and archiving a source. Both are applied optimistically so drag and
 * archive feel instant, then confirmed against the API; a failure surfaces a
 * banner and refetches to restore the server's truth. Editing and creating
 * sources live in the source-detail view, so this hook does not own them.
 */
export function useProfileHub(): { state: ProfileHubState; actions: ProfileHubActions } {
  const client = useSessionClient();
  const [status, setStatus] = useState<HubStatus>("loading");
  const [data, setData] = useState<HubData>(EMPTY_DATA);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    setStatus("loading");
    void (async () => {
      try {
        const [sources, skills, variants] = await Promise.all([
          client.GET("/sources"),
          client.GET("/skills"),
          client.GET("/identity-variants"),
        ]);
        if (!active) return;
        if (!sources.data || !skills.data || !variants.data) {
          setStatus("error");
          return;
        }
        setData({ sources: sources.data, skills: skills.data, variants: variants.data });
        setStatus("ready");
      } catch {
        if (active) setStatus("error");
      }
    })();
    return () => {
      active = false;
    };
  }, [client, reloadToken]);

  const refetch = useCallback(() => setReloadToken((token) => token + 1), []);

  const reorderSources = useCallback(
    (kind: SourceKind, orderedIds: number[]) => {
      setData((current) => ({ ...current, sources: applyReorder(current.sources, kind, orderedIds) }));
      void client
        .POST("/sources/reorder", { body: { kind, source_ids: orderedIds } })
        .then(({ error }) => {
          if (error) {
            setActionError(extractProblem(error).message);
            refetch();
          }
        })
        .catch(() => {
          setActionError("Could not save the new order.");
          refetch();
        });
    },
    [client, refetch],
  );

  const archiveSource = useCallback(
    (id: number) => {
      setData((current) => ({
        ...current,
        sources: current.sources.filter((source) => source.id !== id),
      }));
      void client
        .POST("/sources/{source_id}/archive", { params: { path: { source_id: id } } })
        .then(({ error }) => {
          if (error) {
            setActionError(extractProblem(error).message);
            refetch();
          }
        })
        .catch(() => {
          setActionError("Could not archive that item.");
          refetch();
        });
    },
    [client, refetch],
  );

  const dismissError = useCallback(() => setActionError(null), []);

  return {
    state: { status, data, actionError },
    actions: { reorderSources, archiveSource, dismissError },
  };
}

/** Reassign the reordered kind's `sort_order` to match `orderedIds`; leave other kinds. */
function applyReorder(
  sources: SourceSummary[],
  kind: SourceKind,
  orderedIds: number[],
): SourceSummary[] {
  const inKind = new Map(sources.filter((source) => source.kind === kind).map((s) => [s.id, s]));
  const reordered = orderedIds.flatMap((id, index) => {
    const source = inKind.get(id);
    return source ? [{ ...source, sort_order: index }] : [];
  });
  return [...sources.filter((source) => source.kind !== kind), ...reordered];
}
