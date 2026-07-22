import { useCallback } from "react";

import { useSessionClient } from "@/api";

import type { PublishedVersion } from "../types";

export interface UseResumeHistory {
  /** Fetch the resume's published versions, newest first (may be empty). */
  list: () => Promise<PublishedVersion[]>;
  /** Mint a fresh presigned URL for one version's stored PDF. */
  open: (revisionNo: number) => Promise<string>;
}

/**
 * The two reads behind the History control, over the typed client from the
 * revision routes. `list` returns the published versions (revisions whose PDF was
 * stored by an export or a finalize); `open` mints a time-limited presigned R2 URL
 * for a single version's stored PDF. Both throw on failure so the dialog can show
 * the version-list error or the recoverable per-row "unavailable" state; a missing
 * version or object is a 404, and re-calling `open` re-mints a fresh URL.
 */
export function useResumeHistory(resumeId: number): UseResumeHistory {
  const client = useSessionClient();

  const list = useCallback(async (): Promise<PublishedVersion[]> => {
    const { data, error } = await client.GET("/resumes/{resume_id}/revisions", {
      params: { path: { resume_id: resumeId } },
    });
    if (error || !data) throw new Error("Could not load version history.");
    return data.versions;
  }, [client, resumeId]);

  const open = useCallback(
    async (revisionNo: number): Promise<string> => {
      const { data, error } = await client.GET("/resumes/{resume_id}/revisions/{revision_no}/pdf", {
        params: { path: { resume_id: resumeId, revision_no: revisionNo } },
      });
      if (error || !data) throw new Error("This version's PDF is unavailable.");
      return data.download_url;
    },
    [client, resumeId],
  );

  return { list, open };
}
