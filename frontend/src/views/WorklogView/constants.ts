/** Copy and stable values for the Worklog view. */

/** Deep-link to a bullet in the Library view (owned by the Library slice). */
export const libraryBulletHref = (bulletId: number): string => `/library?bullet=${bulletId}`;

/** Deep-link to a source's detail view (owned by the Profile slice). */
export const sourceDetailHref = (sourceId: number): string => `/profile/sources/${sourceId}`;

export const TIMELINE_ERROR_MESSAGE = "Could not load your worklog.";
export const SEARCH_ERROR_MESSAGE = "Search is unavailable right now.";
export const SAVE_ERROR_MESSAGE = "Could not save your entry. Please try again.";
export const ARCHIVE_ERROR_MESSAGE = "Could not archive that entry. Please try again.";

/** Empty-state copy: a Fraunces display line plus one encouraging primary action. */
export const EMPTY_TITLE = "Start your worklog";
export const EMPTY_BODY = "Capture what you did, one entry at a time. It becomes the raw record your resumes draw from.";

/** Client-side guard messages for the required create/edit fields. */
export const TITLE_REQUIRED_MESSAGE = "A title is required.";
export const DATE_REQUIRED_MESSAGE = "A date is required.";
