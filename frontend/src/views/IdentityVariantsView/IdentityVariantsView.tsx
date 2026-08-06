import { ArrowLeft, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { ErrorBanner } from "@/components/ErrorBanner";
import { Button } from "@/components/ui/button";

import { ReplacementPromptDialog } from "./components/ReplacementPromptDialog";
import { VariantForm } from "./components/VariantForm";
import { VariantRow } from "./components/VariantRow";
import { useIdentityVariants } from "./hooks/useIdentityVariants";

/**
 * Identity variants management: create, edit, set default, and archive the
 * labeled contact sets a resume projects. The one-default and archive-block rules
 * are enforced by the backend; this view surfaces them, including the replacement
 * prompt when archiving a variant a living resume references. Reached from the
 * profile hub's Identity card.
 */
export function IdentityVariantsView() {
  const { state, actions } = useIdentityVariants();
  const [editing, setEditing] = useState<"new" | number | null>(null);

  const editingVariant =
    typeof editing === "number" ? state.variants.find((v) => v.id === editing) : null;
  const isEmpty = state.status === "ready" && state.variants.length === 0;
  // The empty state carries the only primary action, so the header offers one just
  // when there is a list to add to. That keeps one primary call to action on screen
  // and stops it moving as the list resolves.
  const hasHeaderAction = editing === null && state.status === "ready" && !isEmpty;

  return (
    <section className="reading-width flex w-full flex-col gap-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link
            to="/profile"
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
          >
            <ArrowLeft className="size-4" /> Profile
          </Link>
          <h1 className="text-xl font-semibold tracking-tight">Identity variants</h1>
        </div>
        {hasHeaderAction && (
          <Button type="button" size="sm" onClick={() => setEditing("new")}>
            <Plus className="size-3.5" /> New variant
          </Button>
        )}
      </div>

      {state.actionError && (
        <ErrorBanner message={state.actionError} onDismiss={actions.dismissError} />
      )}

      {editing === "new" && (
        <VariantForm
          variant={null}
          forceDefault={state.variants.length === 0}
          onSubmit={actions.create}
          onCancel={() => setEditing(null)}
        />
      )}
      {editingVariant && (
        <VariantForm
          variant={editingVariant}
          forceDefault={false}
          onSubmit={(write) => actions.update(editingVariant.id, write)}
          onCancel={() => setEditing(null)}
        />
      )}

      {state.status === "loading" && (
        <p className="text-muted-foreground text-sm">Loading variants…</p>
      )}
      {state.status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          Could not load your identity variants.
        </p>
      )}
      {isEmpty && editing === null && (
        <div className="flex flex-col items-start gap-3 py-6">
          <p className="display-m text-foreground">No identity variants yet.</p>
          <p className="text-muted-foreground text-sm">
            Add one to project contact details on a resume.
          </p>
          <Button type="button" onClick={() => setEditing("new")}>
            <Plus className="size-3.5" /> New variant
          </Button>
        </div>
      )}
      {state.status === "ready" && state.variants.length > 0 && (
        <ul className="flex flex-col gap-2">
          {state.variants.map((variant) => (
            <VariantRow
              key={variant.id}
              variant={variant}
              onEdit={(id) => setEditing(id)}
              onSetDefault={actions.setDefault}
              onArchive={actions.archive}
            />
          ))}
        </ul>
      )}

      {state.replacementPrompt && (
        <ReplacementPromptDialog
          prompt={state.replacementPrompt}
          candidates={state.variants.filter((v) => v.id !== state.replacementPrompt?.variantId)}
          onCancel={actions.dismissReplacementPrompt}
          onConfirm={actions.archiveWithReplacement}
        />
      )}
    </section>
  );
}
