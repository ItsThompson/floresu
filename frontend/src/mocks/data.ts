import type { components } from "@/api";

type AuthUser = components["schemas"]["AuthenticatedUser"];

/** The demo account the mock harness returns from register/login/me. */
export const mockAuthUser: AuthUser = {
  id: 1,
  email: "demo@floresu.app",
  created_at: "2026-01-01T00:00:00Z",
  has_completed_onboarding: true,
};
