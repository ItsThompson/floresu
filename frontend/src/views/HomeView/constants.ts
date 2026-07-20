import type { FeedEvent } from "./types";

/**
 * Past-tense labels for the closed content-write action set (the backend's
 * `core/events` Action). An unknown action falls back to its raw verb.
 */
const ACTION_LABELS: Record<string, string> = {
  create: "created",
  update: "updated",
  archive: "archived",
  restore: "restored",
  delete: "deleted",
  finalize: "finalized",
  promote: "promoted",
  reorder: "reordered",
  render: "rendered",
  tag: "tagged",
};

export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

/** The affected object's link: a path built from its entity type and id. */
export function entityHref(event: FeedEvent): string {
  return `/${event.entity_type}/${event.entity_id}`;
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
