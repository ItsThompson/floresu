import { screen, waitFor } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { buildFeedEvent } from "@/mocks/data";
import { renderWithProviders } from "@/test/renderWithProviders";

import { ActivityFeed } from "./ActivityFeed";

type Listener = (event: { data: string }) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly listeners: Record<string, Listener[]> = {};
  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, listener: Listener): void {
    (this.listeners[type] ??= []).push(listener);
  }
  close(): void {}
  emit(data: string): void {
    act(() => {
      for (const listener of this.listeners.message ?? []) listener({ data });
    });
  }
}

describe("ActivityFeed", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("renders the initial rows from /feed/history, then live events, deduped", async () => {
    renderWithProviders(<ActivityFeed />);

    // Initial load (MSW returns mockFeedHistory: ids 3, 2, 1). Assert the unique
    // agent row so the query is unambiguous.
    expect(await screen.findByRole("link", { name: "bullet #7" })).toBeInTheDocument();
    expect(screen.getByText("claude")).toBeInTheDocument();

    // The stream opened after the rows rendered.
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];

    // A live event appears...
    source.emit(JSON.stringify(buildFeedEvent({ id: 9, entity_type: "resume", entity_id: 3 })));
    expect(await screen.findByRole("link", { name: "resume #3" })).toBeInTheDocument();

    // ...and a replay of an already-shown id does not duplicate it.
    source.emit(JSON.stringify(buildFeedEvent({ id: 9, entity_type: "resume", entity_id: 3 })));
    expect(screen.getAllByRole("link", { name: "resume #3" })).toHaveLength(1);
  });

  it("shows an inline error when the initial load fails", async () => {
    const { server } = await import("@/mocks/server");
    const { http, HttpResponse } = await import("msw");
    server.use(http.get("*/feed/history", () => new HttpResponse(null, { status: 500 })));

    renderWithProviders(<ActivityFeed />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the activity feed.");
  });
});
