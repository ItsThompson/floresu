import type { ArchivedEntityType } from "./types";

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

/** Human label for each archived entity kind, for the item's type badge. */
export const ENTITY_TYPE_LABEL: Record<ArchivedEntityType, string> = {
  worklog: "Worklog entry",
  source: "Source",
  bullet: "Bullet",
};

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
