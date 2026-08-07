import { useState } from "react";
import { useNavigate } from "react-router";

import { Button } from "@/components/ui/button";
import { resumeEditorPath } from "@/lib/resumePaths";

import { DeleteResumeDialog } from "./components/DeleteResumeDialog";
import { NewResumeDialog } from "./components/NewResumeDialog";
import { ResumeGroupSection } from "./components/ResumeGroupSection";
import { useResumesList } from "./hooks/useResumesList";
import type { ResumeSummary } from "./types";

/**
 * The resumes list: living and application resumes under separate headings, each
 * with a lifecycle badge, plus create and web-only permanent delete. Composition
 * only: `useResumesList` owns the fetch and the write actions; this view wires
 * them to the dialogs and navigates to the editor on open/create.
 */
export function ResumesListView() {
  const navigate = useNavigate();
  const { state, actions } = useResumesList();
  const [isCreating, setIsCreating] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<ResumeSummary | null>(null);

  return (
    <section className="reading-width flex w-full flex-col gap-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Resumes</h1>
        <Button onClick={() => setIsCreating(true)}>+ New resume</Button>
      </header>

      {state.status === "loading" && (
        <p className="text-muted-foreground text-sm">Loading resumes…</p>
      )}

      {state.status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          {state.error}
        </p>
      )}

      {state.status === "ready" && (
        <div className="flex flex-col gap-6">
          <ResumeGroupSection
            heading="Living (role-targeted)"
            emptyMessage="No living resumes yet. Create one to start shaping a direction."
            resumes={state.groups.living}
            onDelete={setPendingDelete}
          />
          <ResumeGroupSection
            heading="Applications"
            emptyMessage="No application resumes yet. Create one from a job application."
            resumes={state.groups.application}
            onDelete={setPendingDelete}
          />
        </div>
      )}

      <NewResumeDialog
        isOpen={isCreating}
        onClose={() => setIsCreating(false)}
        livingResumes={state.groups.living}
        onCreate={actions.create}
        onCreated={(id) => navigate(resumeEditorPath(id))}
      />

      <DeleteResumeDialog
        resume={pendingDelete}
        onClose={() => setPendingDelete(null)}
        onConfirm={actions.remove}
      />
    </section>
  );
}
