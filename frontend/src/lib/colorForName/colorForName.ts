/**
 * Deterministic color for a name, shared across the app.
 *
 * The single source of the identity/tag color palette: the same label always maps
 * to the same color, everywhere it is rendered (agent avatars in the activity
 * feed, audit views, and settings; tag pills). This is a domain truth, not a
 * per-view choice, so it lives in one module and is never re-derived elsewhere.
 *
 * The hash is stable and order-sensitive over the string's code points, and it
 * selects a palette entry by position rather than computing a color, so no color
 * value lives here: the ten hues are `--tag-1` through `--tag-10` in
 * `frontend/src/theme/tokens.css`.
 */

// A frozen contract: entry N is `--tag-(N+1)`, and the hash picks by position, so
// reordering this list repaints every tag and avatar that already exists.
const TAG_PALETTE = [
  "var(--tag-1)",
  "var(--tag-2)",
  "var(--tag-3)",
  "var(--tag-4)",
  "var(--tag-5)",
  "var(--tag-6)",
  "var(--tag-7)",
  "var(--tag-8)",
  "var(--tag-9)",
  "var(--tag-10)",
] as const;

export function colorForName(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    // A classic 31-multiplier rolling hash, kept in 32-bit range with `| 0`.
    hash = (hash * 31 + name.charCodeAt(i)) | 0;
  }
  return TAG_PALETTE[Math.abs(hash) % TAG_PALETTE.length];
}
