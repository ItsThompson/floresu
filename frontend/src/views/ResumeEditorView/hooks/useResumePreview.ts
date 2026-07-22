import { useEffect, useState } from "react";

import { PREVIEW_DEBOUNCE_MS } from "../constants";

export type PreviewStatus = "loading" | "ready" | "error";

export interface UseResumePreviewParams {
  /** Bumped whenever the saved document changes; a new value re-renders the preview. */
  previewKey: number;
  /** Fetch the freshly rendered (ephemeral) PDF bytes for the current document. */
  fetchPreview: () => Promise<Blob>;
}

export interface ResumePreviewState {
  status: PreviewStatus;
  blob: Blob | null;
}

/**
 * Fetches the live PDF preview, debounced by ~0.5s after each edit so a burst of
 * saves collapses into one render. The bytes are ephemeral (never stored). A
 * failed fetch is a render failure: the state goes to `error` so the view shows
 * an error and export is blocked, and a stale image is never presented as current.
 */
export function useResumePreview({ previewKey, fetchPreview }: UseResumePreviewParams): ResumePreviewState {
  const [status, setStatus] = useState<PreviewStatus>("loading");
  const [blob, setBlob] = useState<Blob | null>(null);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    const timer = setTimeout(() => {
      fetchPreview()
        .then((pdf) => {
          if (cancelled) return;
          setBlob(pdf);
          setStatus("ready");
        })
        .catch(() => {
          if (cancelled) return;
          setBlob(null);
          setStatus("error");
        });
    }, PREVIEW_DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [previewKey, fetchPreview]);

  return { status, blob };
}
