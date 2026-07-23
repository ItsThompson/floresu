import { useCallback, useEffect, useState } from "react";

import { useSessionClient } from "@/api";
import type { WriteState } from "@/lib/asyncState";
import { extractProblem } from "@/lib/problemDetail";

import { emptyValues, SOURCE_KIND_CONFIGS } from "../sourceForm";
import type { LoadStatus, SourceFormValues, SourceKind, SourceRecord } from "../types";

interface UseSourceDetailParams {
  /** null in create mode; a numeric id in edit mode. */
  sourceId: number | null;
  /** The kind to create when `sourceId` is null. */
  createKind: SourceKind | null;
  onCreated: (id: number) => void;
  onArchived: () => void;
}

export interface SourceDetail {
  status: LoadStatus;
  kind: SourceKind | null;
  record: SourceRecord | null;
  initial: { values: SourceFormValues; ongoing: boolean } | null;
  write: WriteState;
  fieldErrors: Record<string, string>;
  save: (values: SourceFormValues, ongoing: boolean) => void;
  archive: () => void;
}

/**
 * Owns one source's load, create/update, and archive. In create mode it is ready
 * immediately with an empty form for the requested kind; in edit mode it loads
 * the record and hydrates the form. A save maps its result to a create-navigate
 * or an in-place record update; a failed write surfaces field-level and general
 * errors from the problem body without clearing the form.
 */
export function useSourceDetail({
  sourceId,
  createKind,
  onCreated,
  onArchived,
}: UseSourceDetailParams): SourceDetail {
  const client = useSessionClient();
  const isCreate = sourceId === null;

  const [status, setStatus] = useState<LoadStatus>(isCreate ? "ready" : "loading");
  const [record, setRecord] = useState<SourceRecord | null>(null);
  const [write, setWrite] = useState<WriteState>({ status: "idle" });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (sourceId === null) return;
    let active = true;
    setStatus("loading");
    void client
      .GET("/sources/{source_id}", { params: { path: { source_id: sourceId } } })
      .then(({ data }) => {
        if (!active) return;
        if (!data) {
          setStatus("error");
          return;
        }
        setRecord(data);
        setStatus("ready");
      })
      .catch(() => {
        if (active) setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [client, sourceId]);

  const kind: SourceKind | null = isCreate ? createKind : (record?.kind ?? null);
  const initial = resolveInitial(isCreate, createKind, record);

  const save = useCallback(
    (values: SourceFormValues, ongoing: boolean) => {
      if (!kind) return;
      const body = SOURCE_KIND_CONFIGS[kind].buildWrite(values, ongoing);
      setWrite({ status: "saving" });
      setFieldErrors({});
      const request =
        sourceId === null
          ? client.POST("/sources", { body })
          : client.PUT("/sources/{source_id}", { params: { path: { source_id: sourceId } }, body });
      void request
        .then(({ data, error }) => {
          if (error || !data) {
            applyError(error, setFieldErrors, setWrite);
            return;
          }
          setWrite({ status: "idle" });
          if (sourceId === null) onCreated(data.id);
          else setRecord(data);
        })
        .catch(() => {
          setWrite({ status: "error", message: "Could not save. Please try again." });
        });
    },
    [client, kind, sourceId, onCreated],
  );

  const archive = useCallback(() => {
    if (sourceId === null) return;
    setWrite({ status: "idle" });
    void client
      .POST("/sources/{source_id}/archive", { params: { path: { source_id: sourceId } } })
      .then(({ error }) => {
        if (error) setWrite({ status: "error", message: extractProblem(error).message });
        else onArchived();
      })
      .catch(() => setWrite({ status: "error", message: "Could not archive this source." }));
  }, [client, sourceId, onArchived]);

  return { status, kind, record, initial, write, fieldErrors, save, archive };
}

function resolveInitial(
  isCreate: boolean,
  createKind: SourceKind | null,
  record: SourceRecord | null,
): { values: SourceFormValues; ongoing: boolean } | null {
  if (isCreate) return createKind ? emptyValues(createKind) : null;
  return record ? SOURCE_KIND_CONFIGS[record.kind].toValues(record) : null;
}

/** Map problem field paths (e.g. "body.company") to the form's field names. */
function applyError(
  error: unknown,
  setFieldErrors: (fields: Record<string, string>) => void,
  setWrite: (state: WriteState) => void,
): void {
  const problem = extractProblem(error);
  if (problem.fields) {
    const mapped = Object.entries(problem.fields).reduce<Record<string, string>>(
      (acc, [path, message]) => ({ ...acc, [path.replace(/^body\./, "")]: message }),
      {},
    );
    setFieldErrors(mapped);
  }
  setWrite({ status: "error", message: problem.message });
}
