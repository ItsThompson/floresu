import type { ArchivedEntityType, ArchivedItem, ArchivedItemKey } from "./types";

/**
 * The Settings sub-navigation, in display order. Each section is a nested route
 * under `/settings`; the paths are relative so the nav and the router agree from
 * one source.
 */
export const SETTINGS_SECTIONS = [
  { path: "account", label: "Account" },
  { path: "agents", label: "Connected agents" },
  { path: "archive", label: "Archive & Trash" },
  { path: "data", label: "Data" },
] as const;

/**
 * The single access level every connected agent holds. There is exactly one
 * scope, so this is fixed copy, not a per-scope list.
 */
export const ACCESS_STATEMENT = "Full read-write (single scope).";

/**
 * The treatment for a destructive control that sits in a list row: crimson ink on
 * a ghost button, filling with the crimson tint only on hover. Rows are the calm
 * register, so a row control states its consequence in ink rather than taking a
 * filled crimson block on every row; the filled treatment is reserved for the
 * confirmation that commits the action. Shared by the connected-agent and
 * archived-item rows so the two read as one gesture.
 */
export const DESTRUCTIVE_ROW_ACTION_CLASS =
  "text-destructive hover:bg-destructive-tint hover:text-destructive";

/** Human label for each archived entity kind, for the item's type badge. */
export const ENTITY_TYPE_LABEL: Record<ArchivedEntityType, string> = {
  worklog: "Worklog entry",
  source: "Source",
  bullet: "Bullet",
};

/** Whether a tracked action key refers to a given archived item. */
export function isSameArchivedItem(key: ArchivedItemKey, item: ArchivedItem): boolean {
  return key.entityType === item.entityType && key.id === item.id;
}

/** Format an ISO timestamp as a calendar date (connected-on, archived-on). */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/** Format an ISO timestamp as date and time (last-active). */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
