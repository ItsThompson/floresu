import { renderHook, waitFor } from "@testing-library/react";
import { act } from "react";
import { describe, expect, it, vi } from "vitest";

import { buildFeedEvent } from "@/mocks/data";

import type { FeedConnection, FeedEvent } from "../types";
import { useActivityFeed } from "./useActivityFeed";

/**
 * A controllable fake SSE connection: the test captures the message listener so it
 * can push events and assert the merge/dedup behavior. `close` is spied so unmount
 * cleanup is verifiable.
 */
function fakeConnection() {
  let listener: ((data: string) => void) | null = null;
  const close = vi.fn();
  const connection: FeedConnection = {
    onMessage: (l) => {
      listener = l;
    },
    onError: () => {},
    close,
  };
  const emit = (event: FeedEvent) =>
    act(() => {
      listener?.(JSON.stringify(event));
    });
  const emitRaw = (data: string) =>
    act(() => {
      listener?.(data);
    });
  return { connection, emit, emitRaw, close, isOpen: () => listener !== null };
}

function renderFeed(history: FeedEvent[]) {
  const fake = fakeConnection();
  const loadHistory = vi.fn().mockResolvedValue(history);
  const createConnection = vi.fn(() => fake.connection);
  const view = renderHook(() => useActivityFeed({ loadHistory, createConnection }));
  return { ...view, fake, loadHistory, createConnection };
}

describe("useActivityFeed", () => {
  it("loads the initial rows and opens the stream only after they arrive", async () => {
    const { result, fake, createConnection } = renderFeed([
      buildFeedEvent({ id: 2 }),
      buildFeedEvent({ id: 1 }),
    ]);

    // Starts loading; the connection is not opened until history resolves.
    expect(result.current.status).toBe("loading");
    expect(createConnection).not.toHaveBeenCalled();

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.events.map((event) => event.id)).toEqual([2, 1]);
    expect(fake.isOpen()).toBe(true);
  });

  it("appends a live event, keeping the feed newest-first", async () => {
    const { result, fake } = renderFeed([buildFeedEvent({ id: 1 })]);
    await waitFor(() => expect(result.current.status).toBe("ready"));

    fake.emit(buildFeedEvent({ id: 5 }));

    expect(result.current.events.map((event) => event.id)).toEqual([5, 1]);
  });

  it("does not duplicate an event already shown from the initial load", async () => {
    const { result, fake } = renderFeed([buildFeedEvent({ id: 2 }), buildFeedEvent({ id: 1 })]);
    await waitFor(() => expect(result.current.status).toBe("ready"));

    // A replayed/overlapping event (id already present) must be dropped.
    fake.emit(buildFeedEvent({ id: 2 }));
    fake.emit(buildFeedEvent({ id: 3 }));

    expect(result.current.events.map((event) => event.id)).toEqual([3, 2, 1]);
  });

  it("dedups replayed gap events after a reconnect", async () => {
    const { result, fake } = renderFeed([buildFeedEvent({ id: 10 })]);
    await waitFor(() => expect(result.current.status).toBe("ready"));

    // First stream delivers 11, 12; then a reconnect replays 11, 12 and adds 13.
    fake.emit(buildFeedEvent({ id: 11 }));
    fake.emit(buildFeedEvent({ id: 12 }));
    fake.emit(buildFeedEvent({ id: 11 }));
    fake.emit(buildFeedEvent({ id: 12 }));
    fake.emit(buildFeedEvent({ id: 13 }));

    expect(result.current.events.map((event) => event.id)).toEqual([13, 12, 11, 10]);
  });

  it("ignores a malformed SSE payload without breaking the feed", async () => {
    const { result, fake } = renderFeed([buildFeedEvent({ id: 1 })]);
    await waitFor(() => expect(result.current.status).toBe("ready"));

    // Push a non-JSON frame; the hook must ignore it, not crash.
    fake.emitRaw("not-json{");
    fake.emit(buildFeedEvent({ id: 2 }));

    expect(result.current.events.map((event) => event.id)).toEqual([2, 1]);
  });

  it("surfaces an error state when the initial load fails", async () => {
    const loadHistory = vi.fn().mockRejectedValue(new Error("down"));
    const createConnection = vi.fn();
    const { result } = renderHook(() =>
      useActivityFeed({ loadHistory, createConnection }),
    );

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toBe("Could not load the activity feed.");
    expect(createConnection).not.toHaveBeenCalled();
  });

  it("closes the connection on unmount", async () => {
    const { result, fake, unmount } = renderFeed([buildFeedEvent({ id: 1 })]);
    await waitFor(() => expect(result.current.status).toBe("ready"));

    unmount();
    expect(fake.close).toHaveBeenCalledTimes(1);
  });
});
