import { useCallback, useEffect, useState } from "react";

import { useSessionClient } from "@/api";

import type {
  ResumeCreateRequest,
  ResumeGroups,
  ResumeListStatus,
  ResumesListActions,
  ResumesListState,
  ResumeSummary,
} from "../types";

const EMPTY_GROUPS: ResumeGroups = { living: [], application: [] };

/**
 * Loads the resumes list and exposes create and permanent-delete. The list is
 * grouped into living and application resumes for the two headings. Create and
 * delete re-fetch on success so the list reflects the server truth; a failed
 * write leaves the list untouched and surfaces `false`/`null` to the caller.
 */
export function useResumesList(): { state: ResumesListState; actions: ResumesListActions } {
  const client = useSessionClient();
  const [status, setStatus] = useState<ResumeListStatus>("loading");
  const [groups, setGroups] = useState<ResumeGroups>(EMPTY_GROUPS);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const { data, error: fetchError } = await client.GET("/resumes");
    if (fetchError || !data) {
      setStatus("error");
      setError("Could not load your resumes.");
      return;
    }
    setGroups(groupByKind(data));
    setError(null);
    setStatus("ready");
  }, [client]);

  useEffect(() => {
    void load();
  }, [load]);

  const create = useCallback<ResumesListActions["create"]>(
    async (request: ResumeCreateRequest) => {
      const { data, error: createError } = await client.POST("/resumes", { body: request });
      if (createError || !data) return null;
      await load();
      return data.id;
    },
    [client, load],
  );

  const remove = useCallback<ResumesListActions["remove"]>(
    async (id: number) => {
      const { error: deleteError } = await client.DELETE("/resumes/{resume_id}", {
        params: { path: { resume_id: id }, query: { confirm: true } },
      });
      if (deleteError) return false;
      await load();
      return true;
    },
    [client, load],
  );

  const reload = useCallback(() => void load(), [load]);

  return { state: { status, groups, error }, actions: { create, remove, reload } };
}

/** Split the flat list into the living and application groups the view renders. */
function groupByKind(resumes: ResumeSummary[]): ResumeGroups {
  return resumes.reduce<ResumeGroups>(
    (acc, resume) => {
      acc[resume.kind].push(resume);
      return acc;
    },
    { living: [], application: [] },
  );
}
