import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { usePrefersReducedMotion } from "./usePrefersReducedMotion";

interface FakeMediaQueryList {
  matches: boolean;
  addEventListener: ReturnType<typeof vi.fn>;
  removeEventListener: ReturnType<typeof vi.fn>;
}

function stubMatchMedia(matches: boolean): FakeMediaQueryList {
  const media: FakeMediaQueryList = {
    matches,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => media),
  );
  return media;
}

describe("usePrefersReducedMotion", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("returns true when the OS asks to reduce motion", () => {
    stubMatchMedia(true);
    const { result } = renderHook(() => usePrefersReducedMotion());
    expect(result.current).toBe(true);
  });

  it("returns false when there is no reduced-motion preference", () => {
    stubMatchMedia(false);
    const { result } = renderHook(() => usePrefersReducedMotion());
    expect(result.current).toBe(false);
  });

  it("subscribes to preference changes and cleans up on unmount", () => {
    const media = stubMatchMedia(false);
    const { unmount } = renderHook(() => usePrefersReducedMotion());
    expect(media.addEventListener).toHaveBeenCalledWith("change", expect.any(Function));
    unmount();
    expect(media.removeEventListener).toHaveBeenCalledWith("change", expect.any(Function));
  });
});
