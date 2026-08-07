import type { ResolvedSession } from "../types";

/**
 * Where the primary call to action sends a visitor once the session has resolved.
 * Three outcomes, not two: a signed-in visitor who never finished the wizard
 * lands back in it rather than in an app that has nothing to show them yet.
 */
export function resolveStartDestination(session: ResolvedSession): string {
  if (session.status === "anonymous") return "/signup";
  return session.hasCompletedOnboarding ? "/home" : "/onboarding";
}
