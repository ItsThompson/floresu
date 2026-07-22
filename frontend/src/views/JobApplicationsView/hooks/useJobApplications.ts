import { useCallback, useEffect, useState } from "react";

import { useSessionClient } from "@/api";
import { extractProblem } from "@/lib/problemDetail";

import type {
  JobApplicationsActions,
  JobApplicationsState,
  JobApplicationsStatus,
  JobApplicationSummary,
  ResumeSummary,
} from "../types";

const LOAD_ERROR = "Could not load your job applications.";
const SUBMIT_FALLBACK = "Could not mark this application submitted. Please try again.";

/**
 * Loads the job applications and the resumes they may link to, and exposes the
 * P0 actions: create an application, fork a living resume into a linked
 * application draft, and mark an application submitted (which finalizes its
 * linked resume on the backend). Every write re-fetches on success so the list
 * reflects the server truth. A submit rejection (e.g. no linked resume) is
 * recoverable: the status stays `added` and the reason surfaces via `actionError`.
 */
export function useJobApplications(): {
  state: JobApplicationsState;
  actions: JobApplicationsActions;
} {
  const client = useSessionClient();
  const [status, setStatus] = useState<JobApplicationsStatus>("loading");
  const [applications, setApplications] = useState<JobApplicationSummary[]>([]);
  const [resumes, setResumes] = useState<ResumeSummary[]>([]);
  const [resumesUnavailable, setResumesUnavailable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [appsRes, resumesRes] = await Promise.all([
      client.GET("/job-applications"),
      client.GET("/resumes"),
    ]);
    if (appsRes.error || !appsRes.data) {
      setStatus("error");
      setError(LOAD_ERROR);
      return;
    }
    setApplications(appsRes.data);
    setResumes(resumesRes.data ?? []);
    setResumesUnavailable(!resumesRes.response.ok);
    setError(null);
    setStatus("ready");
  }, [client]);

  useEffect(() => {
    void load();
  }, [load]);

  const create = useCallback<JobApplicationsActions["create"]>(
    async (company, roleTitle) => {
      const { data, error: createError } = await client.POST("/job-applications", {
        body: { company, role_title: roleTitle },
      });
      if (createError || !data) return false;
      await load();
      return true;
    },
    [client, load],
  );

  const linkResume = useCallback<JobApplicationsActions["linkResume"]>(
    async (applicationId, fromResumeId, title) => {
      const { data, error: forkError } = await client.POST("/resumes", {
        body: {
          kind: "application",
          source: { mode: "from_resume", from_resume_id: fromResumeId },
          job_application_id: applicationId,
          title,
        },
      });
      if (forkError || !data) return null;
      await load();
      return data.id;
    },
    [client, load],
  );

  const submit = useCallback<JobApplicationsActions["submit"]>(
    async (applicationId) => {
      setActionError(null);
      const { data, error: submitError } = await client.PATCH(
        "/job-applications/{application_id}",
        {
          params: { path: { application_id: applicationId } },
          body: { status: "submitted" },
        },
      );
      if (submitError || !data) {
        setActionError(extractProblem(submitError, SUBMIT_FALLBACK).message);
        return false;
      }
      await load();
      return true;
    },
    [client, load],
  );

  return {
    state: {
      status,
      applications,
      livingResumes: resumes.filter(
        (resume) => resume.kind === "living" && resume.archived_at === null,
      ),
      resumeTitles: titlesById(resumes),
      resumesUnavailable,
      error,
      actionError,
    },
    actions: {
      reload: () => void load(),
      dismissActionError: () => setActionError(null),
      create,
      linkResume,
      submit,
    },
  };
}

/** A resume title lookup keyed by id, resolving the linked-resume column's label. */
function titlesById(resumes: ResumeSummary[]): Record<number, string> {
  return resumes.reduce<Record<number, string>>((acc, resume) => {
    acc[resume.id] = resume.title;
    return acc;
  }, {});
}
