import { Navigate, Outlet } from "react-router";

import { useAuth } from "@/auth";

/**
 * Gates the in-app routes on onboarding completion. Rendered as a layout route
 * nested inside `RequireAuth`, so the session is already resolved and `user` is
 * present by the time it runs.
 *
 * - not yet onboarded → redirect to the wizard at `/onboarding` (the app shell
 *   never renders, so a non-onboarded user never glimpses it)
 * - onboarded → render the matched in-app route
 */
export function RequireOnboarded() {
  const { user } = useAuth();

  if (user && !user.has_completed_onboarding) {
    return <Navigate to="/onboarding" replace />;
  }
  return <Outlet />;
}
