import { useCallback, useMemo, useState } from "react";
import useSWR from "swr";

import { useSessionClient } from "@/api";

import {
  ARCHIVE_ERROR_MESSAGE,
  SAVE_ERROR_MESSAGE,
  TIMELINE_ERROR_MESSAGE,
} from "../constants";
import type {
  EntryFormValues,
  FormMode,
  MonthGroup,
  SourceSummary,
  WorklogFilters,
  WorklogStatus,
  WorklogSummary,
  WorklogWrite,
  WriteStatus,
} from "../types";
import { filterEntries, groupEntriesByMonth } from "../utils";

const TIMELINE_KEY = "/worklog";
const SOURCES_KEY = "/sources";
const TAGS_KEY = "/worklog/tags";

const NO_FILTERS: WorklogFilters = { sourceId: null, tag: null, dateFrom: null, dateTo: null };

// swr options tuned for a form-driven view under jsdom: revalidation is
// triggered explicitly after a write, so focus/reconnect revalidation only adds
// noise (and unhandled fetches in tests).
const SWR_OPTIONS = { revalidateOnFocus: false, revalidateOnReconnect: false } as const;

export interface WorklogViewState {
  status: WorklogStatus;
  /** Filtered, month-grouped entries ready to render. */
  groups: MonthGroup[];
  /** Active entry count before filtering (drives the empty vs no-match states). */
  totalCount: number;
  sources: SourceSummary[];
  tagOptions: string[];
  filters: WorklogFilters;
  form: FormMode;
  /** Prefilled values when editing; `null` for create or a closed form. */
  editingValues: EntryFormValues | null;
  writeStatus: WriteStatus;
  writeError: string | null;
  archiveError: string | null;
}

export interface WorklogViewActions {
  setSourceFilter: (sourceId: number | null) => void;
  setTagFilter: (tag: string | null) => void;
  setDateRange: (from: string | null, to: string | null) => void;
  clearFilters: () => void;
  openCreate: () => void;
  openEdit: (entryId: number) => void;
  closeForm: () => void;
  submitEntry: (values: EntryFormValues) => Promise<void>;
  archiveEntry: (entryId: number) => Promise<void>;
}

export interface UseWorklog {
  state: WorklogViewState;
  actions: WorklogViewActions;
}

/**
 * Drives the global worklog timeline: reads the entries, sources, and tag list;
 * holds the combined filters and the create/edit form; and performs the audited
 * writes (create, edit, archive) through the typed client, revalidating the
 * timeline on success. Business rules live on the backend; this hook emits
 * intent and reflects results. All three reads and every write go through the
 * generated client, so no endpoint shape is hand-written here.
 */
export function useWorklog(): UseWorklog {
  const client = useSessionClient();

  const timeline = useSWR<WorklogSummary[]>(
    TIMELINE_KEY,
    async () => {
      const { data, error } = await client.GET("/worklog");
      if (error || !data) throw new Error(TIMELINE_ERROR_MESSAGE);
      return data;
    },
    SWR_OPTIONS,
  );

  const sources = useSWR<SourceSummary[]>(
    SOURCES_KEY,
    async () => {
      const { data, error } = await client.GET("/sources");
      if (error || !data) throw new Error("Could not load sources.");
      return data;
    },
    SWR_OPTIONS,
  );

  const tags = useSWR(
    TAGS_KEY,
    async () => {
      const { data, error } = await client.GET("/worklog/tags");
      if (error || !data) throw new Error("Could not load tags.");
      return data;
    },
    SWR_OPTIONS,
  );

  const [filters, setFilters] = useState<WorklogFilters>(NO_FILTERS);
  const [form, setForm] = useState<FormMode>({ kind: "closed" });
  const [writeStatus, setWriteStatus] = useState<WriteStatus>("idle");
  const [writeError, setWriteError] = useState<string | null>(null);
  const [archiveError, setArchiveError] = useState<string | null>(null);

  const entries = useMemo(() => timeline.data ?? [], [timeline.data]);
  const groups = useMemo(
    () => groupEntriesByMonth(filterEntries(entries, filters)),
    [entries, filters],
  );
  const tagOptions = useMemo(() => (tags.data ?? []).map((tag) => tag.label), [tags.data]);

  const editingValues = useMemo<EntryFormValues | null>(() => {
    if (form.kind !== "edit") return null;
    const entry = entries.find((candidate) => candidate.id === form.entryId);
    if (!entry) return null;
    return {
      title: entry.title,
      entryDate: entry.entry_date,
      description: entry.description ?? "",
      tags: entry.tags,
      sourceIds: entry.source_ids,
    };
  }, [form, entries]);

  const status: WorklogStatus = timeline.error
    ? "error"
    : timeline.data === undefined
      ? "loading"
      : "ready";

  const openCreate = useCallback(() => {
    setWriteStatus("idle");
    setWriteError(null);
    setForm({ kind: "create" });
  }, []);

  const openEdit = useCallback((entryId: number) => {
    setWriteStatus("idle");
    setWriteError(null);
    setForm({ kind: "edit", entryId });
  }, []);

  const closeForm = useCallback(() => {
    setForm({ kind: "closed" });
    setWriteStatus("idle");
    setWriteError(null);
  }, []);

  const submitEntry = useCallback(
    async (values: EntryFormValues) => {
      const body: WorklogWrite = {
        title: values.title.trim(),
        entry_date: values.entryDate,
        description: values.description.trim() === "" ? null : values.description.trim(),
        tags: values.tags,
        source_ids: values.sourceIds,
      };

      setWriteStatus("saving");
      setWriteError(null);
      try {
        const request =
          form.kind === "edit"
            ? client.PUT("/worklog/{worklog_id}", {
                params: { path: { worklog_id: form.entryId } },
                body,
              })
            : client.POST("/worklog", { body });
        const { error, response } = await request;
        if (error || !response.ok) throw new Error(SAVE_ERROR_MESSAGE);
        await Promise.all([timeline.mutate(), tags.mutate()]);
        setWriteStatus("idle");
        setForm({ kind: "closed" });
      } catch {
        setWriteStatus("error");
        setWriteError(SAVE_ERROR_MESSAGE);
      }
    },
    [client, form, timeline, tags],
  );

  const archiveEntry = useCallback(
    async (entryId: number) => {
      setArchiveError(null);
      try {
        const { error, response } = await client.POST("/worklog/{worklog_id}/archive", {
          params: { path: { worklog_id: entryId } },
        });
        if (error || !response.ok) throw new Error(ARCHIVE_ERROR_MESSAGE);
        await timeline.mutate();
      } catch {
        setArchiveError(ARCHIVE_ERROR_MESSAGE);
      }
    },
    [client, timeline],
  );

  const actions = useMemo<WorklogViewActions>(
    () => ({
      setSourceFilter: (sourceId) => setFilters((prev) => ({ ...prev, sourceId })),
      setTagFilter: (tag) => setFilters((prev) => ({ ...prev, tag })),
      setDateRange: (from, to) => setFilters((prev) => ({ ...prev, dateFrom: from, dateTo: to })),
      clearFilters: () => setFilters(NO_FILTERS),
      openCreate,
      openEdit,
      closeForm,
      submitEntry,
      archiveEntry,
    }),
    [openCreate, openEdit, closeForm, submitEntry, archiveEntry],
  );

  return {
    state: {
      status,
      groups,
      totalCount: entries.length,
      sources: sources.data ?? [],
      tagOptions,
      filters,
      form,
      editingValues,
      writeStatus,
      writeError,
      archiveError,
    },
    actions,
  };
}
