import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PREVIEW_DEBOUNCE_MS } from "../constants";
import { useResumePreview } from "./useResumePreview";

const pdfBlob = () => new Blob(["%PDF"], { type: "application/pdf" });
const settle = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

describe("useResumePreview", () => {
  it("does not fetch until the debounce elapses, then renders ready", async () => {
    const fetchPreview = vi.fn().mockResolvedValue(pdfBlob());
    const { result } = renderHook(() => useResumePreview({ previewKey: 0, fetchPreview }));

    expect(result.current.status).toBe("loading");
    expect(fetchPreview).not.toHaveBeenCalled();

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(fetchPreview).toHaveBeenCalledTimes(1);
    expect(result.current.blob).toBeInstanceOf(Blob);
  });

  it("goes to error and drops the blob when the fetch fails (render failure)", async () => {
    const fetchPreview = vi.fn().mockRejectedValue(new Error("render failed"));
    const { result } = renderHook(() => useResumePreview({ previewKey: 0, fetchPreview }));

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.blob).toBeNull();
  });

  it("re-fetches when the preview key changes", async () => {
    const fetchPreview = vi.fn().mockResolvedValue(pdfBlob());
    const { rerender } = renderHook(({ previewKey }) => useResumePreview({ previewKey, fetchPreview }), {
      initialProps: { previewKey: 0 },
    });

    await waitFor(() => expect(fetchPreview).toHaveBeenCalledTimes(1));
    rerender({ previewKey: 1 });
    await waitFor(() => expect(fetchPreview).toHaveBeenCalledTimes(2));
  });

  it("collapses a burst of key changes into a single fetch (debounce)", async () => {
    const fetchPreview = vi.fn().mockResolvedValue(pdfBlob());
    const { rerender } = renderHook(({ previewKey }) => useResumePreview({ previewKey, fetchPreview }), {
      initialProps: { previewKey: 0 },
    });

    rerender({ previewKey: 1 });
    rerender({ previewKey: 2 });
    await settle(PREVIEW_DEBOUNCE_MS + 150);

    expect(fetchPreview).toHaveBeenCalledTimes(1);
  });
});
