import type { components } from "@/api";

/** A connected agent (OAuth client) as the connected-agents list renders it. */
export type ConnectedClient = components["schemas"]["ConnectedClient"];

/** The three archivable entity kinds the Archive & Trash panel manages. */
export type ArchivedEntityType = "worklog" | "source" | "bullet";

/**
 * A single archived item, unified across the three domains so the Archive & Trash
 * panel can list, restore, and permanently delete them through one shape. The
 * `entityType` selects the correct restore and delete routes.
 */
export interface ArchivedItem {
  entityType: ArchivedEntityType;
  id: number;
  label: string;
  archivedAt: string;
}

/** Identifies one archived item for in-flight action tracking. */
export interface ArchivedItemKey {
  entityType: ArchivedEntityType;
  id: number;
}
