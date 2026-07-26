/**
 * Past-tense labels for the closed content-write action set (the backend's
 * `core/events` Action). Shared by every audit-read surface (the activity feed
 * and per-item history) so an action reads the same everywhere. An unknown action
 * falls back to its raw verb.
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
