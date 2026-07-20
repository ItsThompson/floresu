/**
 * The browser-navigation boundary. Isolating `window.location` here gives the
 * one external side effect a named seam that callers inject and tests mock,
 * instead of reaching into the global directly.
 */

/** Navigate the browser to an absolute URL (a full-page, cross-origin navigation). */
export function assignLocation(url: string): void {
  window.location.assign(url);
}
