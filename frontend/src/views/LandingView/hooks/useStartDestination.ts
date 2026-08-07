import { useAuth } from "@/auth";

import type { StartDestination } from "../types";
import { resolveStartDestination } from "../util/resolveStartDestination";

/**
 * The auth-aware destination for the primary call to action, or `null` while the
 * session is still resolving, so the control renders disabled rather than briefly
 * pointing a returning visitor at signup.
 */
export function useStartDestination(): StartDestination | null {
  const { status, user } = useAuth();

  if (status === "loading") return null;
  if (status === "anonymous") {
    return { path: resolveStartDestination({ status }), isSignedIn: false };
  }
  return {
    path: resolveStartDestination({
      status,
      hasCompletedOnboarding: user?.has_completed_onboarding ?? false,
    }),
    isSignedIn: true,
  };
}
