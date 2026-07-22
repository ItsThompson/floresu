import { useCallback, useEffect, useMemo, useState } from "react";

import { useSessionClient } from "@/api";

import {
  ARCHIVE_ERROR_FALLBACK,
  DEFAULT_FILTERS,
  SAVE_ERROR_FALLBACK,
  SEARCH_ERROR_MESSAGE,
} from "../constants";
import type {
  BulletFormValues,
  BulletWrite,
  LibraryActions,
  LibraryData,
  LibraryEditor,
  LibraryFilters,
  LibraryState,
  SearchState,
} from "../types";
import { errorMessage, toSearchFilters } from "../utils";

interface UseLibrary {
  state: LibraryState;
  actions: LibraryActions;
}

const EMPTY_DATA: LibraryData = {
  status: "loading",
  sources: [],
  bullets: [],
  worklogEntries: [],
  tags: [],
};

/**
 * The Library screen's single state owner: it loads the four datasets the view
 * needs (sources, bullets, worklog, tags), runs hybrid search, and drives the
 * bullet create/edit/archive writes. It calls the session client directly (the
 * app's established boundary) and holds no business rules: grouping and filter
 * mapping live in pure `utils`, and every everywhere/embedding rule is enforced
 * by the backend. Writes refresh the bullet list and re-run an active search so
 * an edit or archive is reflected without a manual reload.
 */
export function useLibrary(): UseLibrary {
  const client = useSessionClient();

  const [data, setData] = useState<LibraryData>(EMPTY_DATA);
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<LibraryFilters>(DEFAULT_FILTERS);
  const [search, setSearch] = useState<SearchState>({ status: "idle" });
  const [editor, setEditor] = useState<LibraryEditor | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [archiveError, setArchiveError] = useState<string | null>(null);

  const fetchAll = useCallback(async (): Promise<LibraryData | null> => {
    try {
      const [sources, bullets, worklog, tags] = await Promise.all([
        client.GET("/sources"),
        client.GET("/bullets"),
        client.GET("/worklog"),
        client.GET("/worklog/tags"),
      ]);
      if (
        sources.error ||
        !sources.data ||
        bullets.error ||
        !bullets.data ||
        worklog.error ||
        !worklog.data ||
        tags.error ||
        !tags.data
      ) {
        return null;
      }
      return {
        status: "ready",
        sources: sources.data,
        bullets: bullets.data,
        worklogEntries: worklog.data,
        tags: tags.data,
      };
    } catch {
      return null;
    }
  }, [client]);

  useEffect(() => {
    let active = true;
    setData((prev) => ({ ...prev, status: "loading" }));
    void fetchAll().then((next) => {
      if (!active) return;
      setData((prev) => next ?? { ...prev, status: "error" });
    });
    return () => {
      active = false;
    };
  }, [fetchAll]);

  const refreshBullets = useCallback(async () => {
    const { data: bullets, error } = await client.GET("/bullets");
    if (error || !bullets) return;
    setData((prev) => ({ ...prev, bullets }));
  }, [client]);

  const runSearch = useCallback(
    async (rawQuery: string, activeFilters: LibraryFilters) => {
      const trimmed = rawQuery.trim();
      if (trimmed === "") {
        setSearch({ status: "idle" });
        return;
      }
      setSearch({ status: "searching" });
      const { data: result, error } = await client.POST("/search", {
        body: { query: trimmed, filters: toSearchFilters(activeFilters) },
      });
      if (error || !result) {
        setSearch({ status: "error", message: SEARCH_ERROR_MESSAGE });
        return;
      }
      setSearch({ status: "results", result });
    },
    [client],
  );

  // Re-run search after a write, but only while results are already on screen,
  // so an edit or archive updates the visible hits without a manual re-query.
  // The status check stays out of any state updater so it is not double-invoked
  // under StrictMode (which would fire a duplicate POST /search).
  const rerunActiveSearch = useCallback(() => {
    if (search.status === "results") void runSearch(query, filters);
  }, [runSearch, query, filters, search.status]);

  const saveBullet = useCallback(
    (values: BulletFormValues) => {
      const body: BulletWrite = {
        text: values.text,
        source_ids: values.sourceIds,
        worklog_ids: values.worklogIds,
      };
      setIsSaving(true);
      setSaveError(null);
      const request =
        editor?.mode === "edit"
          ? client.PUT("/bullets/{bullet_id}", {
              params: {
                path: { bullet_id: editor.bullet.id },
                // Send the loaded revision so the backend CAS guards the write. The
                // recoverable 409 re-read/retry UX is a separate follow-up; here a
                // stale save surfaces as a save error rather than a false success.
                header: { "If-Match": editor.bullet.revision },
              },
              body,
            })
          : client.POST("/bullets", { body });
      void request.then(async ({ data: saved, error }) => {
        setIsSaving(false);
        if (error || !saved) {
          setSaveError(errorMessage(error, SAVE_ERROR_FALLBACK));
          return;
        }
        setEditor(null);
        await refreshBullets();
        rerunActiveSearch();
      });
    },
    [client, editor, refreshBullets, rerunActiveSearch],
  );

  const archiveBullet = useCallback(
    (bulletId: number) => {
      setArchiveError(null);
      void client
        .POST("/bullets/{bullet_id}/archive", { params: { path: { bullet_id: bulletId } } })
        .then(async ({ data: archived, error }) => {
          if (error || !archived) {
            setArchiveError(errorMessage(error, ARCHIVE_ERROR_FALLBACK));
            return;
          }
          await refreshBullets();
          rerunActiveSearch();
        });
    },
    [client, refreshBullets, rerunActiveSearch],
  );

  const actions = useMemo<LibraryActions>(
    () => ({
      setQuery,
      updateFilters: (patch) => setFilters((prev) => ({ ...prev, ...patch })),
      submitSearch: () => void runSearch(query, filters),
      clearSearch: () => {
        setQuery("");
        setSearch({ status: "idle" });
      },
      openCreate: () => {
        setSaveError(null);
        setEditor({ mode: "create" });
      },
      openEdit: (bullet) => {
        setSaveError(null);
        setEditor({ mode: "edit", bullet });
      },
      closeEditor: () => {
        setEditor(null);
        setSaveError(null);
      },
      saveBullet,
      archiveBullet,
      reload: () => {
        setData((prev) => ({ ...prev, status: "loading" }));
        void fetchAll().then((next) => setData((prev) => next ?? { ...prev, status: "error" }));
      },
    }),
    [runSearch, query, filters, saveBullet, archiveBullet, fetchAll],
  );

  const state = useMemo<LibraryState>(
    () => ({ data, query, filters, search, editor, isSaving, saveError, archiveError }),
    [data, query, filters, search, editor, isSaving, saveError, archiveError],
  );

  return { state, actions };
}
