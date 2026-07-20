import { useAuth } from "@/auth";
import { RouteLoading } from "@/components/RouteLoading";
import { assignLocation } from "@/lib/browserNavigation";

import { ConsentCard } from "./components/ConsentCard";
import { ConsentError } from "./components/ConsentError";
import { useConsent } from "./hooks/useConsent";

/**
 * OAuth consent screen (chrome-free, centered card). Mounted behind the session
 * guard, so an unauthenticated visitor authenticates first and returns here; by
 * the time this renders the user is signed in. Composes the consent state
 * machine with the card / error / loading surfaces. The decision navigates the
 * browser to the agent's redirect URL, which is cross-origin (a loopback
 * listener or https callback) and known only after the decision POST returns, so
 * a real link is not possible: this is the sanctioned programmatic-navigation
 * case, injected via `assignLocation`.
 */
export function ConsentView() {
  const { user } = useAuth();
  const { state, actions } = useConsent({ redirect: assignLocation });

  if (state.phase === "loading") {
    return <RouteLoading />;
  }
  if (state.phase === "error") {
    return <ConsentError message={state.message} />;
  }
  return (
    <ConsentCard
      agentName={state.agentName}
      userEmail={user?.email ?? ""}
      isDeciding={state.phase === "deciding"}
      onApprove={actions.approve}
      onDeny={actions.deny}
    />
  );
}
