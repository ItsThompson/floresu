import type { SessionClient } from "@/api";

import type { ArchivedItem } from "../types";

/**
 * The boundary calls for the Archive & Trash panel, one per archivable domain.
 * Kept apart from the state hook so the per-entity route dispatch lives in one
 * place and the hook stays free of endpoint literals.
 *
 * Listing reads each domain with `include_archived`, then keeps only the rows the
 * user has archived (a non-null `archived_at`), mapping them to the unified
 * `ArchivedItem` shape the panel renders. Restore and permanent delete select the
 * route by entity type; delete passes `confirm: true`, the API-level gate the
 * confirmation UI stands in front of.
 */
export async function loadArchivedItems(client: SessionClient): Promise<ArchivedItem[]> {
  const [worklog, sources, bullets] = await Promise.all([
    client.GET("/worklog", { params: { query: { include_archived: true } } }),
    client.GET("/sources", { params: { query: { include_archived: true } } }),
    client.GET("/bullets", { params: { query: { include_archived: true } } }),
  ]);

  if (worklog.error || sources.error || bullets.error) {
    throw new Error("archive load failed");
  }

  const items: ArchivedItem[] = [];
  for (const entry of worklog.data ?? []) {
    if (entry.archived_at) {
      items.push({
        entityType: "worklog",
        id: entry.id,
        label: entry.title,
        archivedAt: entry.archived_at,
      });
    }
  }
  for (const source of sources.data ?? []) {
    if (source.archived_at) {
      items.push({
        entityType: "source",
        id: source.id,
        label: source.display_label,
        archivedAt: source.archived_at,
      });
    }
  }
  for (const bullet of bullets.data ?? []) {
    if (bullet.archived_at) {
      items.push({
        entityType: "bullet",
        id: bullet.id,
        label: bullet.text,
        archivedAt: bullet.archived_at,
      });
    }
  }
  return items;
}

/** Restore one archived item to its active views (and, where applicable, search). */
export async function restoreArchivedItem(
  client: SessionClient,
  item: ArchivedItem,
): Promise<void> {
  const { error } = await restoreCall(client, item);
  if (error) throw new Error("restore failed");
}

/** Permanently delete one item. Passes the API-level `confirm` gate. */
export async function deleteArchivedItem(
  client: SessionClient,
  item: ArchivedItem,
): Promise<void> {
  const { error } = await deleteCall(client, item);
  if (error) throw new Error("delete failed");
}

function restoreCall(client: SessionClient, item: ArchivedItem) {
  switch (item.entityType) {
    case "worklog":
      return client.POST("/worklog/{worklog_id}/restore", {
        params: { path: { worklog_id: item.id } },
      });
    case "source":
      return client.POST("/sources/{source_id}/restore", {
        params: { path: { source_id: item.id } },
      });
    case "bullet":
      return client.POST("/bullets/{bullet_id}/restore", {
        params: { path: { bullet_id: item.id } },
      });
  }
}

function deleteCall(client: SessionClient, item: ArchivedItem) {
  switch (item.entityType) {
    case "worklog":
      return client.DELETE("/worklog/{worklog_id}", {
        params: { path: { worklog_id: item.id }, query: { confirm: true } },
      });
    case "source":
      return client.DELETE("/sources/{source_id}", {
        params: { path: { source_id: item.id }, query: { confirm: true } },
      });
    case "bullet":
      return client.DELETE("/bullets/{bullet_id}", {
        params: { path: { bullet_id: item.id }, query: { confirm: true } },
      });
  }
}
