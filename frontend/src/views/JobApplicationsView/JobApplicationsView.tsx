import { useCallback, useState } from "react";
import { useNavigate } from "react-router";

import { ErrorBanner } from "@/components/ErrorBanner";
import { Button } from "@/components/ui/button";
import { resumeEditorPath } from "@/lib/resumePaths";

import { JobApplicationsTable } from "./components/JobApplicationsTable";
import { LinkResumeDialog } from "./components/LinkResumeDialog";
import { NewJobApplicationDialog } from "./components/NewJobApplicationDialog";
import { SubmitConfirmDialog } from "./components/SubmitConfirmDialog";
import { useJobApplications } from "./hooks/useJobApplications";
import type { JobApplicationSummary } from "./types";

/**
 * The Job Applications screen: a table of applications with the create flow, the
 * fork-a-resume flow, opening a linked resume, and the confirm-gated mark-submitted
 * action that finalizes the linked resume. Composition only: `useJobApplications`
 * owns the fetch and every write; this view wires them to the table and dialogs.
 *
 * A table, so it stays calm: hairlines, quiet metadata, and tinted status pills
 * carry the page. The header's add action is the view's only loud element, so the
 * empty state invites in words rather than repeating the button, and it holds the
 * view's one serif display moment.
 */
export function JobApplicationsView() {
  const navigate = useNavigate();
  const { state, actions } = useJobApplications();
  const [isCreating, setIsCreating] = useState(false);
  const [linkTarget, setLinkTarget] = useState<JobApplicationSummary | null>(null);
  const [submit, setSubmit] = useState<{
    application: JobApplicationSummary;
    isSubmitting: boolean;
  } | null>(null);

  const confirmSubmit = useCallback(async () => {
    if (submit === null) return;
    setSubmit({ application: submit.application, isSubmitting: true });
    await actions.submit(submit.application.id);
    setSubmit(null);
  }, [actions, submit]);

  return (
    <section className="reading-width flex w-full flex-col gap-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Job Applications</h1>
        <Button onClick={() => setIsCreating(true)}>+ New application</Button>
      </header>

      {state.actionError && (
        <ErrorBanner message={state.actionError} onDismiss={actions.dismissActionError} />
      )}

      {state.resumesUnavailable && (
        <p role="alert" className="text-muted-foreground text-sm">
          Couldn’t load your resumes, so resume links and creating a resume are temporarily
          unavailable. Your job applications are still shown.
        </p>
      )}

      {state.status === "loading" && (
        <p className="text-muted-foreground text-sm">Loading job applications…</p>
      )}

      {state.status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          {state.error}
        </p>
      )}

      {state.status === "ready" &&
        (state.applications.length === 0 ? (
          <div className="flex flex-col gap-1">
            <p className="display-m">No job applications yet.</p>
            <p className="text-muted-foreground">Add one to start tracking where you applied.</p>
          </div>
        ) : (
          <JobApplicationsTable
            applications={state.applications}
            resumeTitles={state.resumeTitles}
            onLinkResume={setLinkTarget}
            onSubmit={(application) => setSubmit({ application, isSubmitting: false })}
          />
        ))}

      <NewJobApplicationDialog
        isOpen={isCreating}
        onClose={() => setIsCreating(false)}
        onCreate={actions.create}
      />

      <LinkResumeDialog
        application={linkTarget}
        livingResumes={state.livingResumes}
        resumesUnavailable={state.resumesUnavailable}
        onClose={() => setLinkTarget(null)}
        onLink={actions.linkResume}
        onLinked={(resumeId) => {
          setLinkTarget(null);
          navigate(resumeEditorPath(resumeId));
        }}
      />

      <SubmitConfirmDialog
        application={submit?.application ?? null}
        isSubmitting={submit?.isSubmitting ?? false}
        onConfirm={() => void confirmSubmit()}
        onCancel={() => setSubmit(null)}
      />
    </section>
  );
}
