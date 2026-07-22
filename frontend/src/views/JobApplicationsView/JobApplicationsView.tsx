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
 */
export function JobApplicationsView() {
  const navigate = useNavigate();
  const { state, actions } = useJobApplications();
  const [isCreating, setIsCreating] = useState(false);
  const [linkTarget, setLinkTarget] = useState<JobApplicationSummary | null>(null);
  const [submitTarget, setSubmitTarget] = useState<JobApplicationSummary | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const confirmSubmit = useCallback(async () => {
    if (submitTarget === null) return;
    setIsSubmitting(true);
    await actions.submit(submitTarget.id);
    setIsSubmitting(false);
    setSubmitTarget(null);
  }, [actions, submitTarget]);

  return (
    <section className="mx-auto flex w-full max-w-[960px] flex-col gap-8 p-8">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Job Applications</h1>
        <Button onClick={() => setIsCreating(true)}>+ New application</Button>
      </header>

      {state.actionError && (
        <ErrorBanner message={state.actionError} onDismiss={actions.dismissActionError} />
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
          <p className="text-muted-foreground text-sm">
            No job applications yet. Add one to start tracking where you applied.
          </p>
        ) : (
          <JobApplicationsTable
            applications={state.applications}
            resumeTitles={state.resumeTitles}
            onLinkResume={setLinkTarget}
            onSubmit={setSubmitTarget}
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
        onClose={() => setLinkTarget(null)}
        onLink={actions.linkResume}
        onLinked={(resumeId) => {
          setLinkTarget(null);
          navigate(resumeEditorPath(resumeId));
        }}
      />

      <SubmitConfirmDialog
        application={submitTarget}
        isSubmitting={isSubmitting}
        onConfirm={() => void confirmSubmit()}
        onCancel={() => setSubmitTarget(null)}
      />
    </section>
  );
}
