import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createFeedConnection } from "./feedConnection";

type Listener = (event: { data: string }) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  readonly withCredentials: boolean;
  readonly listeners: Record<string, Listener[]> = {};
  closed = false;

  constructor(url: string, init?: { withCredentials?: boolean }) {
    this.url = url;
    this.withCredentials = init?.withCredentials ?? false;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: Listener): void {
    (this.listeners[type] ??= []).push(listener);
  }

  close(): void {
    this.closed = true;
  }

  dispatch(type: string, event: { data: string }): void {
    for (const listener of this.listeners[type] ?? []) listener(event);
  }
}

describe("createFeedConnection", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("opens a credentialed EventSource against the API origin's /feed", () => {
    createFeedConnection("http://api.example");
    const source = FakeEventSource.instances[0];
    expect(source.url).toBe("http://api.example/feed");
    expect(source.withCredentials).toBe(true);
  });

  it("forwards message payloads to the onMessage listener", () => {
    const connection = createFeedConnection("");
    const received: string[] = [];
    connection.onMessage((data) => received.push(data));

    FakeEventSource.instances[0].dispatch("message", { data: "hello" });
    expect(received).toEqual(["hello"]);
  });

  it("forwards errors and closes the underlying source", () => {
    const connection = createFeedConnection("");
    const onError = vi.fn();
    connection.onError(onError);

    FakeEventSource.instances[0].dispatch("error", { data: "" });
    expect(onError).toHaveBeenCalledTimes(1);

    connection.close();
    expect(FakeEventSource.instances[0].closed).toBe(true);
  });
});
