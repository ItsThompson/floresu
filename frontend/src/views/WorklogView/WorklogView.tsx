import { Button } from "@/components/ui/button";

import {
  EMPTY_BODY,
  EMPTY_TITLE,
  TIMELINE_ERROR_MESSAGE,
} from "./constants";
import { WorklogEntryForm } from "./components/WorklogEntryForm";
import { WorklogFilters } from "./components/WorklogFilters";
import { WorklogSearch } from "./components/WorklogSearch";
import { WorklogTimeline } from "./components/WorklogTimeline";
import { useWorklog } from "./hooks/useWorklog";
import { useWorklogSearch } from "./hooks/useWorklogSearch";

/**
 * The Worklog screen: a month-grouped global timeline with combined filters, an
 * embedded hybrid-search field, and the create/edit/archive flows. A thin
 * orchestrator: it composes the data/write hook and the search hook, then wires
 * their state and intent into the presentational parts. All rules live on the
 * backend.
 */
export function WorklogView() {
  const { state, actions } = useWorklog();
  const search = useWorklogSearch();

  const isEmpty = state.status === "ready" && state.totalCount === 0;
  const hasNoMatches = state.status === "ready" && state.totalCount > 0 && state.groups.length === 0;

  return (
    <section className="mx-auto flex w-full max-w-[860px] flex-col gap-6 p-8">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Worklog</h1>
        <Button onClick={actions.openCreate}>+ Add entry</Button>
      </header>

      <WorklogFilters
        sources={state.sources}
        tagOptions={state.tagOptions}
        filters={state.filters}
        onSourceChange={actions.setSourceFilter}
        onTagChange={actions.setTagFilter}
        onDateRangeChange={actions.setDateRange}
        onClear={actions.clearFilters}
      />

      <WorklogSearch state={search.state} actions={search.actions} />

      {state.form.kind !== "closed" && (
        <WorklogEntryForm
          key={state.form.kind === "edit" ? `edit-${state.form.entryId}` : "create"}
          mode={state.form.kind === "edit" ? "edit" : "create"}
          initialValues={state.editingValues}
          sources={state.sources}
          isSaving={state.write.status === "saving"}
          error={state.write.status === "error" ? state.write.message : null}
          onSubmit={(values) => void actions.submitEntry(values)}
          onCancel={actions.closeForm}
        />
      )}

      {state.archiveError && (
        <p role="alert" className="text-destructive text-sm">
          {state.archiveError}
        </p>
      )}

      {state.status === "loading" && <p className="text-muted-foreground text-sm">Loading your worklog…</p>}

      {state.status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          {TIMELINE_ERROR_MESSAGE}
        </p>
      )}

      {isEmpty && (
        <div className="flex flex-col items-start gap-3 py-8">
          <h2 className="text-xl font-semibold">{EMPTY_TITLE}</h2>
          <p className="text-muted-foreground max-w-prose">{EMPTY_BODY}</p>
          <Button onClick={actions.openCreate}>Add your first entry</Button>
        </div>
      )}

      {hasNoMatches && (
        <p className="text-muted-foreground text-sm">No entries match your filters.</p>
      )}

      {state.status === "ready" && state.groups.length > 0 && (
        <WorklogTimeline
          groups={state.groups}
          sources={state.sources}
          onEdit={actions.openEdit}
          onArchive={actions.archiveEntry}
        />
      )}
    </section>
  );
}
