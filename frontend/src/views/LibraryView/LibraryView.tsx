import { useMemo } from "react";

import { Button } from "@/components/ui/button";

import { BrowseGroups } from "./components/BrowseGroups";
import { BulletForm } from "./components/BulletForm";
import { LibraryToolbar } from "./components/LibraryToolbar";
import { SearchFilters } from "./components/SearchFilters";
import { SearchResults } from "./components/SearchResults";
import { EMPTY_LIBRARY_MESSAGE, LOAD_ERROR_MESSAGE } from "./constants";
import { useLibrary } from "./hooks/useLibrary";
import type { BulletFormValues } from "./types";
import { groupBulletsBySource } from "./utils";

/**
 * The Library screen: bullets grouped by source, an embedded hybrid search over
 * the same corpus that powers the agent's search tool, and canonical bullet
 * create/edit/archive. Composition only: state, data, search, and writes live in
 * `useLibrary`; grouping lives in `utils`; every everywhere/embedding rule is the
 * backend's. Browse (grouped bullets) is the resting view; a submitted query
 * swaps in ranked results, and clearing it returns to browse.
 */
export function LibraryView() {
  const { state, actions } = useLibrary();
  const { data, search, editor } = state;

  const groups = useMemo(
    () => groupBulletsBySource(data.bullets, data.sources),
    [data.bullets, data.sources],
  );

  if (data.status === "loading") {
    return (
      <section className="mx-auto w-full max-w-[860px] p-8">
        <p className="text-muted-foreground text-sm">Loading your library…</p>
      </section>
    );
  }

  if (data.status === "error") {
    return (
      <section className="mx-auto flex w-full max-w-[860px] flex-col items-start gap-3 p-8">
        <p role="alert" className="text-destructive text-sm">
          {LOAD_ERROR_MESSAGE}
        </p>
        <Button type="button" variant="outline" onClick={actions.reload}>
          Try again
        </Button>
      </section>
    );
  }

  const editorInitialValues: BulletFormValues =
    editor?.mode === "edit"
      ? {
          text: editor.bullet.text,
          sourceIds: editor.bullet.source_ids,
          worklogIds: editor.bullet.worklog_ids,
        }
      : { text: "", sourceIds: [], worklogIds: [] };

  return (
    <section className="mx-auto flex w-full max-w-[860px] flex-col gap-6 p-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Library</h1>
        <p className="text-muted-foreground">
          Your reusable bullet framings, grouped by source. Search ranks across your worklog and
          bullets.
        </p>
      </header>

      <LibraryToolbar
        query={state.query}
        isSearching={search.status === "searching"}
        hasActiveSearch={search.status !== "idle"}
        onQueryChange={actions.setQuery}
        onSubmit={actions.submitSearch}
        onClear={actions.clearSearch}
        onNewBullet={actions.openCreate}
      />

      <SearchFilters
        sources={data.sources}
        tags={data.tags}
        filters={state.filters}
        onChange={actions.updateFilters}
      />

      {editor && (
        <BulletForm
          mode={editor.mode}
          initialValues={editorInitialValues}
          sources={data.sources}
          worklogEntries={data.worklogEntries}
          isSaving={state.isSaving}
          error={state.saveError}
          onSubmit={actions.saveBullet}
          onCancel={actions.closeEditor}
        />
      )}

      {state.archiveError && (
        <p role="alert" className="text-destructive text-sm">
          {state.archiveError}
        </p>
      )}

      {search.status === "searching" && <p className="text-muted-foreground text-sm">Searching…</p>}

      {search.status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          {search.message}
        </p>
      )}

      {search.status === "results" && <SearchResults result={search.result} />}

      {search.status === "idle" &&
        (groups.length > 0 ? (
          <BrowseGroups
            groups={groups}
            onEdit={actions.openEdit}
            onArchive={actions.archiveBullet}
          />
        ) : (
          <p className="text-muted-foreground text-sm">{EMPTY_LIBRARY_MESSAGE}</p>
        ))}
    </section>
  );
}
