import type { FeedConnection } from "./types";

const FEED_PATH = "/feed";

/**
 * The live feed connection over the browser's `EventSource`.
 *
 * `withCredentials` sends the session cookie to the API origin (same-origin in dev
 * via the Vite proxy; the API subdomain in prod). `EventSource` reconnects on its
 * own and resends the last `id:` it saw as `Last-Event-ID`, which the server uses
 * to replay the gap, so this wrapper only forwards messages/errors and closes.
 */
export function createFeedConnection(baseUrl: string): FeedConnection {
  const source = new EventSource(`${baseUrl}${FEED_PATH}`, { withCredentials: true });
  return {
    onMessage: (listener) => {
      source.addEventListener("message", (event) => listener(event.data));
    },
    onError: (listener) => {
      source.addEventListener("error", () => listener());
    },
    close: () => source.close(),
  };
}
