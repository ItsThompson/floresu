import type { components } from "@/api";

type AuthUser = components["schemas"]["AuthenticatedUser"];
type FeedEvent = components["schemas"]["AuditEntry"];

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

/**
 * Build an activity-feed event fixture. Defaults to a human "create" on a worklog;
 * override `actor_type`/`actor_label` for an agent event, or `id` for ordering.
 */
export function buildFeedEvent(overrides?: Partial<FeedEvent>): FeedEvent {
  return {
    id: 1,
    actor_type: "human",
    actor_label: null,
    entity_type: "worklog",
    entity_id: 100,
    action: "create",
    summary: null,
    metadata: null,
    created_at: "2026-07-20T12:00:00Z",
    ...overrides,
  };
}

/** The demo feed rows the mock harness returns from /feed/history (newest-first). */
export const mockFeedHistory: FeedEvent[] = [
  buildFeedEvent({ id: 3, action: "tag", entity_type: "worklog", entity_id: 12 }),
  buildFeedEvent({
    id: 2,
    actor_type: "agent",
    actor_label: "claude",
    action: "update",
    entity_type: "bullet",
    entity_id: 7,
  }),
  buildFeedEvent({ id: 1, action: "create", entity_type: "worklog", entity_id: 12 }),
];
