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
      <h2 className="text-lg font-semibold tracking-tight">Activity</h2>

      {status === "loading" && (
        <p className="text-sm text-muted-foreground">Loading activity…</p>
      )}

      {status === "error" && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {status === "ready" && events.length === 0 && (
        <p className="text-sm text-muted-foreground">No activity yet.</p>
      )}

      {status === "ready" && events.length > 0 && (
        <ul className="flex flex-col gap-2">
          {events.map((event) => (
            <FeedRow key={event.id} event={event} animate={!prefersReducedMotion} />
          ))}
        </ul>
      )}
    </section>
  );
}
