import type { FeedEvent } from "./types";

/**
 * Route builders per entity type, each mapping to a path that exists in
 * `routes.tsx`. Builders for a detail route take the entity id; those that open a
 * list ignore it. Mirrors the `libraryBulletHref`/`sourceDetailHref` builders so
 * a feed link opens the same target as the rest of the app.
 */
const ENTITY_HREF_BUILDERS: Record<string, (entityId: number) => string> = {
  resume: (entityId) => `/resumes/${entityId}`,
  bullet: (entityId) => `/library?bullet=${entityId}`,
  source: (entityId) => `/profile/sources/${entityId}`,
  worklog: () => "/worklog",
  job_application: () => "/applications",
  identity_variant: () => "/profile/identities",
  skill: () => "/profile/skills",
};

/** Where an unknown entity_type degrades to: the app root, never a broken link. */
export const ENTITY_HREF_FALLBACK = "/";

/** The affected object's link: a route that exists for the event's entity type. */
export function entityHref(event: FeedEvent): string {
  const build = ENTITY_HREF_BUILDERS[event.entity_type];
  return build ? build(event.entity_id) : ENTITY_HREF_FALLBACK;
}

/** The affected object's visible label: its summary, or the type and id. */
export function entityLabel(event: FeedEvent): string {
  return event.summary?.trim() || `${event.entity_type} #${event.entity_id}`;
}

/**
 * Upper bound on rendered feed rows. A long-lived Home tab would otherwise grow
 * the events array and DOM without limit; the feed shows the newest window and
 * older rows are recoverable via a reload. Comfortably above the history page size.
 */
export const MAX_RENDERED_EVENTS = 100;

/**
 * How many worklog entries the Home recent-worklog preview shows. A fixed preview
 * cap, not the full timeline; the worklog view owns the complete history.
 */
export const WORKLOG_PREVIEW_COUNT = 5;
