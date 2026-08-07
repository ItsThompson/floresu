/**
 * Deep-links to the route that owns each entity kind. Shared so every surface
 * that references an entity (a timeline row, a search hit, an activity-feed row)
 * opens the same target.
 */

/** A bullet in the Library view. */
export function libraryBulletHref(bulletId: number): string {
  return `/library?bullet=${bulletId}`;
}

/** A profile source's detail view. */
export function sourceDetailHref(sourceId: number): string {
  return `/profile/sources/${sourceId}`;
}
