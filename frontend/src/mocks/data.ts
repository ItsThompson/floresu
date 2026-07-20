import type { components } from "@/api";

type AuthUser = components["schemas"]["AuthenticatedUser"];

/**
 * Build an authenticated-user fixture. Defaults to a completed-onboarding demo
 * account; override `has_completed_onboarding` (or any field) for the states a
 * test needs, e.g. a fresh user who must still see the wizard.
 */
export function buildAuthUser(overrides?: Partial<AuthUser>): AuthUser {
  return {
    id: 1,
    email: "demo@floresu.app",
    created_at: "2026-01-01T00:00:00Z",
    has_completed_onboarding: true,
    ...overrides,
  };
}

/** The demo account the mock harness returns from register/login/me. */
export const mockAuthUser: AuthUser = buildAuthUser();
