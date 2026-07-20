/**
 * Deterministic color for a name, shared across the app.
 *
 * The single source of the identity/tag color palette: the same label always maps
 * to the same color, everywhere it is rendered (agent avatars in the activity
 * feed, audit views, and settings; tag pills). This is a domain truth, not a
 * per-view choice, so it lives in one module and is never re-derived elsewhere.
 *
 * The hash is stable and order-sensitive over the string's code points; the color
 * is an `hsl()` with a hashed hue and fixed saturation/lightness, so every
 * generated color is legible and mutually distinguishable without a lookup table.
 */

// Fixed saturation/lightness keep avatars legible against a light surface and
// distinct from the coral reserved for the human actor.
const SATURATION_PERCENT = 65;
const LIGHTNESS_PERCENT = 45;

export function colorForName(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    // A classic 31-multiplier rolling hash, kept in 32-bit range with `| 0`.
    hash = (hash * 31 + name.charCodeAt(i)) | 0;
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue} ${SATURATION_PERCENT}% ${LIGHTNESS_PERCENT}%)`;
}
