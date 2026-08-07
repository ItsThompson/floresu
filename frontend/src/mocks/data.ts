import type { components } from "@/api";

import { buildEntry } from "./worklogFixtures";

type AuthUser = components["schemas"]["AuthenticatedUser"];
type FeedEvent = components["schemas"]["AuditEntry"];
type SourceSummary = components["schemas"]["SourceSummary"];
type SourceRecord = components["schemas"]["SourceRecord"];
type SkillRead = components["schemas"]["SkillRead"];
type IdentityVariantRead = components["schemas"]["IdentityVariantRead"];
type BulletpointRecord = components["schemas"]["BulletpointRecord"];
type WorklogSummary = components["schemas"]["WorklogSummary"];

/**
 * Build an authenticated-user fixture. Defaults to a completed-onboarding demo
 * account; override `has_completed_onboarding` (or any field) for the states a
 * test needs, e.g. a fresh user who must still see the wizard.
 */
export function buildAuthUser(overrides?: Partial<AuthUser>): AuthUser {
  return {
    id: 1,
    email: "demo@floresu.com",
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

// --- Career Profile fixtures ---------------------------------------------

/** Build a source list-row (common columns only). Defaults to an ongoing role. */
export function buildSourceSummary(overrides?: Partial<SourceSummary>): SourceSummary {
  return {
    id: 100,
    kind: "role",
    display_label: "Acme — Engineer",
    date_start: "2024-01-01",
    date_end: null,
    summary: null,
    sort_order: 0,
    archived_at: null,
    ...overrides,
  };
}

/** Build a full source record with its typed subtype detail joined in. */
export function buildSourceRecord(overrides?: Partial<SourceRecord>): SourceRecord {
  return {
    id: 100,
    kind: "role",
    display_label: "Acme — Engineer",
    date_start: "2024-01-01",
    date_end: null,
    summary: "Built things.",
    sort_order: 0,
    archived_at: null,
    detail: { company: "Acme", job_title: "Engineer", title_aliases: [], location: null },
    ...overrides,
  };
}

/** Build a curated skill with a derived usage count. */
export function buildSkill(overrides?: Partial<SkillRead>): SkillRead {
  return { id: 200, name: "React", usage_count: 0, sort_order: 0, archived_at: null, ...overrides };
}

/** Build an identity variant. Defaults to a non-default variant with an email. */
export function buildVariant(overrides?: Partial<IdentityVariantRead>): IdentityVariantRead {
  return {
    id: 300,
    label: "Default",
    full_name: "Taylor Dev",
    contact: { email: "taylor@floresu.com", phone: null, location: null },
    links: [],
    is_default: false,
    archived_at: null,
    ...overrides,
  };
}

/** Build a canonical bullet framing. */
export function buildBullet(overrides?: Partial<BulletpointRecord>): BulletpointRecord {
  return {
    id: 400,
    text: "Improved engagement 35%.",
    source_ids: [100],
    worklog_ids: [],
    used_in_count: 1,
    revision: 1,
    archived_at: null,
    ...overrides,
  };
}

/**
 * Build a profile-context worklog row (attached to the demo source #100).
 * Derived from the canonical `buildEntry` so the row shape and shared defaults
 * live in one place; the profile deviations (source #100, no tags, no
 * description) stay explicit here.
 */
export function buildWorklogSummary(overrides?: Partial<WorklogSummary>): WorklogSummary {
  return buildEntry({ id: 500, source_ids: [100], description: null, tags: [], ...overrides });
}
