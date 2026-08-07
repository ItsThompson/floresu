import { useCallback } from "react";

import { useApiBaseUrl, useSessionClient } from "@/api";

import { createFeedConnection } from "../feedConnection";
import { useActivityFeed } from "../hooks/useActivityFeed";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";
import type { CreateFeedConnection, LoadFeedHistory } from "../types";
import { FeedRow } from "./FeedRow";

/**
 * The live activity feed on Home. Loads the recent audit rows, then streams live
 * events over SSE and renders them by actor, action, object link, and time.
 *
 * Composition only: the load and connection boundaries are built here from the
 * session client and the API origin and handed to `useActivityFeed`, which owns
 * the merge/dedup/ordering.
 *
 * The feed is where Home is allowed to be loud: the bloom dot marks an open
 * stream, and the newest row carries the accent tint. The dot appears only once
 * the stream is open, and the word beside it carries the same state, so the color
 * is never the only signal.
 */
export function ActivityFeed() {
  const client = useSessionClient();
  const baseUrl = useApiBaseUrl();
  const prefersReducedMotion = usePrefersReducedMotion();

  const loadHistory = useCallback<LoadFeedHistory>(async () => {
    const { data, error } = await client.GET("/feed/history");
    if (error || !data) throw new Error("Failed to load the activity feed.");
    return data;
  }, [client]);

  const createConnection = useCallback<CreateFeedConnection>(
    () => createFeedConnection(baseUrl),
    [baseUrl],
  );

  const { status, events, error } = useActivityFeed({ loadHistory, createConnection });

  return (
    <section aria-label="Activity feed" className="flex flex-col gap-3">
      <header className="border-border flex items-center gap-3 border-b pb-2">
        <h2 className="text-lg font-semibold tracking-tight">Activity</h2>
        {status === "ready" && (
          <span className="mono-meta text-muted-foreground ml-auto inline-flex items-center gap-2 uppercase">
            <span
              aria-hidden="true"
              data-testid="feed-live-dot"
              className="bg-bloom size-2 animate-pulse rounded-full"
            />
            live
          </span>
        )}
      </header>

      {status === "loading" && <p className="text-muted-foreground text-sm">Loading activity…</p>}

      {status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      {status === "ready" && events.length === 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-sm">No activity yet.</p>
          <p className="text-muted-foreground text-sm">
            Everything you and your agents write shows up here as it happens.
          </p>
        </div>
      )}

      {status === "ready" && events.length > 0 && (
        <ul className="divide-border/60 flex flex-col divide-y">
          {events.map((event, index) => (
            <FeedRow
              key={event.id}
              event={event}
              animate={!prefersReducedMotion}
              isNewest={index === 0}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
