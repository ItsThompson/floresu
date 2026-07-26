/** The worklog route. */
export const WORKLOG_PATH = "/worklog";

/**
 * Query flag on `/worklog` that opens a fresh new-entry form on arrival. The
 * onboarding manual cold-start sets it so the user lands on an open form.
 */
export const NEW_ENTRY_PARAM = "new";

/** The worklog route with the new-entry form open on arrival. */
export function worklogNewEntryPath(): string {
  return `${WORKLOG_PATH}?${NEW_ENTRY_PARAM}=1`;
}
