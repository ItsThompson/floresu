import { useCallback, useMemo, useState } from "react";

import { useSessionClient } from "@/api";
import { useAuth } from "@/auth";

const DELETE_ERROR = "Couldn't delete your account. Try again.";

/**
 * Account-data state.
 *
 * `status`  `deleting` while the account delete is in flight, `error` on failure.
 * `error`   set only in the `error` status.
 */
export interface AccountDataState {
  status: "idle" | "deleting" | "error";
  error: string | null;
}

export interface AccountDataActions {
  deleteAccount: () => void;
}

interface UseAccountData {
  state: AccountDataState;
  actions: AccountDataActions;
}

/**
 * Drives account deletion. Deleting calls the web-only lifecycle route with the
 * API-level `confirm` gate; the server removes the user's records and revokes
 * every connected agent. On success it clears the local session (the server has
 * already invalidated the cookie), which sends the now-anonymous user back to
 * sign-in. Data export is a plain credentialed download link, so it needs no
 * action here. This hook holds no destructive logic itself: the teardown is the
 * server's.
 */
export function useAccountData(): UseAccountData {
  const client = useSessionClient();
  const { logout } = useAuth();
  const [state, setState] = useState<AccountDataState>({ status: "idle", error: null });

  const deleteAccount = useCallback(() => {
    setState({ status: "deleting", error: null });
    void client
      .DELETE("/account", { params: { query: { confirm: true } } })
      .then(({ error }) => {
        if (error) {
          setState({ status: "error", error: DELETE_ERROR });
          return;
        }
        void logout();
      })
      .catch(() => {
        setState({ status: "error", error: DELETE_ERROR });
      });
  }, [client, logout]);

  const actions = useMemo<AccountDataActions>(() => ({ deleteAccount }), [deleteAccount]);

  return { state, actions };
}
