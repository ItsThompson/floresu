import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import { useSessionClient } from "@/api";

import { DECISION_FAILED_MESSAGE, INVALID_REQUEST_MESSAGE } from "../constants";
import type { ConsentActions, ConsentState, UseConsentParams } from "../types";

interface UseConsent {
  state: ConsentState;
  actions: ConsentActions;
}

/**
 * Drives the OAuth consent screen for one parked authorization request.
 *
 * On mount it reads the opaque `auth_request_id` from the URL and fetches the
 * parked request's context (the agent name) from the AS. The human's decision
 * posts to the AS, which mints a one-time code (approve) or nothing (deny) and
 * returns the agent's redirect URL; the hook then navigates the browser there
 * via the injected `redirect`. The session client carries the human's cookie, so
 * the AS gates the decision on the signed-in user. This hook holds no token
 * logic: the code mint lives entirely on the AS.
 */
export function useConsent({ redirect }: UseConsentParams): UseConsent {
  const client = useSessionClient();
  const [searchParams] = useSearchParams();
  const authRequestId = searchParams.get("auth_request_id");

  const [state, setState] = useState<ConsentState>({ phase: "loading" });

  useEffect(() => {
    if (!authRequestId) {
      setState({ phase: "error", message: INVALID_REQUEST_MESSAGE });
      return;
    }
    // Guard against a resolved fetch writing state after the id changed/unmounted.
    let active = true;
    setState({ phase: "loading" });
    void client
      .GET("/oauth/authorize/context", {
        params: { query: { auth_request_id: authRequestId } },
      })
      .then(({ data }) => {
        if (!active) return;
        setState(
          data
            ? { phase: "ready", agentName: data.client_name }
            : { phase: "error", message: INVALID_REQUEST_MESSAGE },
        );
      })
      .catch(() => {
        if (!active) return;
        setState({ phase: "error", message: INVALID_REQUEST_MESSAGE });
      });
    return () => {
      active = false;
    };
  }, [authRequestId, client]);

  const decide = useCallback(
    (approve: boolean) => {
      if (!authRequestId) return;
      // Only a shown card can decide; keep the agent name so the card stays put
      // with its actions disabled while the decision is in flight.
      setState((current) =>
        current.phase === "ready" ? { phase: "deciding", agentName: current.agentName } : current,
      );
      void client
        .POST("/oauth/authorize/decision", {
          body: { auth_request_id: authRequestId, approve },
        })
        .then(({ data }) => {
          if (data) {
            redirect(data.redirect_uri);
            return;
          }
          setState({ phase: "error", message: DECISION_FAILED_MESSAGE });
        })
        .catch(() => {
          setState({ phase: "error", message: DECISION_FAILED_MESSAGE });
        });
    },
    [authRequestId, client, redirect],
  );

  const actions = useMemo<ConsentActions>(
    () => ({ approve: () => decide(true), deny: () => decide(false) }),
    [decide],
  );

  return { state, actions };
}
