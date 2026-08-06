import { ArrowLeft } from "lucide-react";
import { Link } from "react-router";

import { ErrorBanner } from "@/components/ErrorBanner";
import { useDragReorder } from "@/lib/reorder";

import { AddSkillForm } from "./components/AddSkillForm";
import { SkillRow } from "./components/SkillRow";
import { useSkills } from "./hooks/useSkills";

/**
 * Skills management: add, rename, reorder, and archive curated skills, each
 * showing its derived usage count. Reached from the profile hub's Skills card.
 * The exactly-curated rule (no auto-promotion from tags) is preserved by only
 * ever adding through the explicit form.
 */
export function SkillsView() {
  const { state, actions } = useSkills();
  const ids = state.skills.map((skill) => skill.id);
  const { draggingId, handleProps } = useDragReorder(ids, (next) =>
    actions.reorder(next as number[]),
  );

  return (
    <section className="reading-width flex w-full flex-col gap-6">
      <div className="flex items-center gap-3">
        <Link
          to="/profile"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
        >
          <ArrowLeft className="size-4" /> Profile
        </Link>
        <h1 className="text-xl font-semibold tracking-tight">Skills</h1>
      </div>

      <AddSkillForm onAdd={actions.create} />

      {state.actionError && (
        <ErrorBanner message={state.actionError} onDismiss={actions.dismissError} />
      )}

      {state.status === "loading" && (
        <p className="text-muted-foreground text-sm">Loading skills…</p>
      )}
      {state.status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          Could not load your skills.
        </p>
      )}
      {state.status === "ready" && state.skills.length === 0 && (
        <div className="flex flex-col gap-1">
          <p className="display-m">No skills yet.</p>
          <p className="text-muted-foreground">Add the skills your resumes should present.</p>
        </div>
      )}
      {state.status === "ready" && state.skills.length > 0 && (
        <ul className="divide-border/60 flex flex-col divide-y">
          {state.skills.map((skill) => (
            <SkillRow
              key={skill.id}
              skill={skill}
              handleProps={handleProps(skill.id)}
              isDragging={draggingId === skill.id}
              onRename={actions.rename}
              onArchive={actions.archive}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
