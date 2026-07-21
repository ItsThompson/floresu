import { useCallback, useEffect, useMemo, useState } from "react";

import { useSessionClient } from "@/api";

import type { ConnectedClient } from "../types";

const LOAD_ERROR = "Couldn't load your connected agents.";
const REVOKE_ERROR = "Couldn't revoke that agent. Try again.";

/**
 * Connected-agents state.
 *
 * `status`      the load lifecycle for the client list.
 * `clients`     the connected agents, once loaded.
 * `loadError`   set only in the `error` status.
 * `revokingId`  the client id whose revoke is in flight (disables its control).
 * `revokeError` a failed revoke, surfaced without discarding the list.
 */
export interface ConnectedAgentsState {
  status: "loading" | "ready" | "error";
  clients: ConnectedClient[];
  loadError: string | null;
  revokingId: string | null;
  revokeError: string | null;
}

export interface ConnectedAgentsActions {
  revoke: (clientId: string) => void;
}

interface UseConnectedAgents {
  state: ConnectedAgentsState;
  actions: ConnectedAgentsActions;
}

/**
 * Drives the connected-agents list: loads the agents on mount and revokes one on
 * request. Revoking calls the OAuth server's revoke route; on success the agent
 * drops from the list (it can reconnect only through fresh consent). This hook
 * holds no destructive logic of its own: the grant teardown lives on the server.
 */
export function useConnectedAgents(): UseConnectedAgents {
  const client = useSessionClient();
  const [state, setState] = useState<ConnectedAgentsState>({
    status: "loading",
    clients: [],
    loadError: null,
    revokingId: null,
    revokeError: null,
  });

  useEffect(() => {
    let active = true;
    setState((prev) => ({ ...prev, status: "loading", loadError: null }));
    void client
      .GET("/me/clients")
      .then(({ data }) => {
        if (!active) return;
        setState((prev) =>
          data
            ? { ...prev, status: "ready", clients: data, loadError: null }
            : { ...prev, status: "error", loadError: LOAD_ERROR },
        );
      })
      .catch(() => {
        if (!active) return;
        setState((prev) => ({ ...prev, status: "error", loadError: LOAD_ERROR }));
      });
    return () => {
      active = false;
    };
  }, [client]);

  const revoke = useCallback(
    (clientId: string) => {
      setState((prev) => ({ ...prev, revokingId: clientId, revokeError: null }));
      void client
        .DELETE("/me/clients/{client_id}", { params: { path: { client_id: clientId } } })
        .then(({ error }) => {
          setState((prev) =>
            error
              ? { ...prev, revokingId: null, revokeError: REVOKE_ERROR }
              : {
                  ...prev,
                  revokingId: null,
                  clients: prev.clients.filter((c) => c.client_id !== clientId),
                },
          );
        })
        .catch(() => {
          setState((prev) => ({ ...prev, revokingId: null, revokeError: REVOKE_ERROR }));
        });
    },
    [client],
  );

  const actions = useMemo<ConnectedAgentsActions>(() => ({ revoke }), [revoke]);

  return { state, actions };
}
