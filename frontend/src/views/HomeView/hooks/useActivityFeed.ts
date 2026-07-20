import { useEffect, useState } from "react";

import type {
  ActivityFeedState,
  FeedEvent,
  FeedStatus,
  UseActivityFeedParams,
} from "../types";

/**
 * Drives the live activity feed: load the recent audit rows, then open the SSE
 * stream and merge events in as they arrive.
 *
 * Dedup + ordering: events are keyed by their monotonic `id` and kept
 * newest-first. A reconnect replays the gap (the browser's `EventSource` resends
 * `Last-Event-ID` and the server replays buffered events), and any event already
 * shown, including from the initial load, is dropped by the id merge, so nothing
 * renders twice.
 *
 * The history loader and the connection factory are injected (the boundaries to
 * the API and the browser `EventSource`), which keeps this hook a pure,
 * independently testable unit.
 */
export function useActivityFeed({
  loadHistory,
  createConnection,
}: UseActivityFeedParams): ActivityFeedState {
  const [status, setStatus] = useState<FeedStatus>("loading");
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let connection: ReturnType<UseActivityFeedParams["createConnection"]> | null = null;

    loadHistory()
      .then((history) => {
        if (cancelled) return;
        setEvents(history);
        setStatus("ready");
        // Open the stream only once the initial rows are in, so the first live
        // events merge against a rendered baseline (spec: connect after render).
        connection = createConnection();
        connection.onMessage((data) => {
          const incoming = parseEvent(data);
          if (incoming) setEvents((current) => mergeById(current, incoming));
        });
      })
      .catch(() => {
        if (cancelled) return;
        setStatus("error");
        setError("Could not load the activity feed.");
      });

    return () => {
      cancelled = true;
      connection?.close();
    };
  }, [loadHistory, createConnection]);

  return { status, events, error };
}

/** Insert an event newest-first, skipping ids already present (dedup). */
function mergeById(events: FeedEvent[], incoming: FeedEvent): FeedEvent[] {
  if (events.some((event) => event.id === incoming.id)) return events;
  return [incoming, ...events].sort((a, b) => b.id - a.id);
}

/** Parse one SSE `data:` payload into an event, or null if it is malformed. */
function parseEvent(data: string): FeedEvent | null {
  try {
    return JSON.parse(data) as FeedEvent;
  } catch {
    return null;
  }
}
