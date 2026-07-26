import { useCallback, useEffect, useRef, useState } from "react";

import { useSessionClient } from "@/api";
import type { LoadState, WriteState } from "@/lib/asyncState";
import { extractProblem } from "@/lib/problemDetail";

import { toResumeUpdate, withLocalItemText, withNewSection } from "../documentOps";
import type {
  BulletpointRecord,
  IdentityVariant,
  ResumeEditScope,
  ResumeEditor,
  ResumeItem,
  ResumeRecord,
  ScopePromptContext,
  SectionKind,
  TemplateInfo,
} from "../types";

const SAVE_ERROR = "Your change could not be saved. Please try again.";
const FINALIZE_ERROR = "This resume could not be finalized. Please try again.";

/**
 * The resume editor's state and write actions. It loads the resume, the canonical
 * bullets its items reference, the identity variants, and the templates, then
 * exposes every edit the form performs. Every write carries the current revision
 * as `If-Match`; a 409 enters the write `stale` state so the view can prompt to
 * re-read (last-write-wins is never silent). Editing a library_ref item runs the
 * copy-on-write scope flow; the view renders the prompt and never decides scope.
 */
export function useResumeEditor(resumeId: number): ResumeEditor {
  const client = useSessionClient();
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [record, setRecordState] = useState<ResumeRecord | null>(null);
  const [bullets, setBullets] = useState<Record<number, BulletpointRecord>>({});
  const [variants, setVariants] = useState<IdentityVariant[]>([]);
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [writeState, setWriteState] = useState<WriteState>({ status: "idle" });
  const [scopePrompt, setScopePrompt] = useState<ScopePromptContext | null>(null);
  const [previewKey, setPreviewKey] = useState(0);

  // A ref mirrors the record so actions always read the latest revision for the
  // `If-Match` guard without being recreated on every save.
  const recordRef = useRef<ResumeRecord | null>(null);
  const applyRecord = useCallback((next: ResumeRecord) => {
    recordRef.current = next;
    setRecordState(next);
    setPreviewKey((key) => key + 1);
  }, []);

  const refreshBullets = useCallback(async () => {
    const { data } = await client.GET("/bullets");
    if (data) setBullets(indexById(data));
  }, [client]);

  const load = useCallback(async () => {
    setLoadState({ status: "loading" });
    setWriteState({ status: "idle" });
    setScopePrompt(null);
    const [resumeRes, bulletsRes, variantsRes, templatesRes] = await Promise.all([
      client.GET("/resumes/{resume_id}", { params: { path: { resume_id: resumeId } } }),
      client.GET("/bullets"),
      client.GET("/identity-variants"),
      client.GET("/resumes/templates"),
    ]);
    if (resumeRes.error || !resumeRes.data) {
      setLoadState({ status: "error", message: "Could not load this resume." });
      return;
    }
    recordRef.current = resumeRes.data;
    setRecordState(resumeRes.data);
    setBullets(indexById(bulletsRes.data ?? []));
    setVariants(variantsRes.data ?? []);
    setTemplates(templatesRes.data ?? []);
    setLoadState({ status: "ready" });
  }, [client, resumeId]);

  useEffect(() => {
    void load();
  }, [load]);

  /** Run a record-returning write, mapping 409 → stale and other errors → inline. */
  const runWrite = useCallback(
    async (call: () => Promise<WriteResult>): Promise<boolean> => {
      setWriteState({ status: "saving" });
      const { data, error: writeError, response } = await call();
      if (response.status === 409) {
        setWriteState({ status: "stale" });
        return false;
      }
      if (writeError || !data) {
        setWriteState({ status: "error", message: extractProblem(writeError, SAVE_ERROR).message });
        return false;
      }
      applyRecord(data);
      setWriteState({ status: "idle" });
      return true;
    },
    [applyRecord],
  );

  /** Header carrying the current revision as the optimistic `If-Match` token. */
  const ifMatch = () => ({ "If-Match": recordRef.current?.revision ?? 0 });

  const submitBulletEdit = useCallback(
    async (bulletId: number, newText: string, scope?: ResumeEditScope) => {
      const current = recordRef.current;
      if (!current) return;
      setWriteState({ status: "saving" });
      const {
        data,
        error: editError,
        response,
      } = await client.POST("/resumes/bullet-edit", {
        body: {
          bullet_id: bulletId,
          new_text: newText,
          scope: scope ?? null,
          resume_id: current.id,
          if_match_resume_revision: current.revision,
          if_match_bullet_revision: bullets[bulletId]?.revision ?? null,
        },
      });
      if (response.status === 409) {
        // A concurrent change conflicts: drop any open scope prompt so the stale
        // re-read dialog does not stack over a lingering scope dialog.
        setScopePrompt(null);
        setWriteState({ status: "stale" });
        return;
      }
      if (editError || !data) {
        setWriteState({ status: "error", message: extractProblem(editError, SAVE_ERROR).message });
        return;
      }
      if (data.outcome === "prompt") {
        setScopePrompt({ bulletId, newText, usedInCount: data.used_in_count });
        setWriteState({ status: "idle" });
        return;
      }
      setScopePrompt(null);
      if (data.outcome === "forked_this_resume") applyRecord(data.resume);
      else setPreviewKey((key) => key + 1);
      await refreshBullets();
      setWriteState({ status: "idle" });
    },
    [client, bullets, applyRecord, refreshBullets],
  );

  const editItemText = useCallback<ResumeEditor["actions"]["editItemText"]>(
    (item: ResumeItem, newText: string) => {
      const current = recordRef.current;
      if (!current) return;
      if (item.kind === "library_ref") {
        void submitBulletEdit(item.bullet_id, newText);
        return;
      }
      void runWrite(() =>
        client.PUT("/resumes/{resume_id}", {
          params: { path: { resume_id: current.id }, header: ifMatch() },
          body: withLocalItemText(current, item.id, newText),
        }),
      );
    },
    [client, runWrite, submitBulletEdit],
  );

  const putUpdate = useCallback(
    (overrides: Parameters<typeof toResumeUpdate>[1]) => {
      const current = recordRef.current;
      if (!current) return;
      void runWrite(() =>
        client.PUT("/resumes/{resume_id}", {
          params: { path: { resume_id: current.id }, header: ifMatch() },
          body: toResumeUpdate(current, overrides),
        }),
      );
    },
    [client, runWrite],
  );

  const actions: ResumeEditor["actions"] = {
    reload: () => void load(),
    dismissStale: () => setWriteState({ status: "idle" }),
    editItemText,
    resolveScope: (scope) => {
      if (scopePrompt) void submitBulletEdit(scopePrompt.bulletId, scopePrompt.newText, scope);
    },
    cancelScope: () => setScopePrompt(null),
    addSection: (kind: SectionKind, title: string) => {
      const current = recordRef.current;
      if (!current) return;
      void runWrite(() =>
        client.PUT("/resumes/{resume_id}", {
          params: { path: { resume_id: current.id }, header: ifMatch() },
          body: withNewSection(current, kind, title),
        }),
      );
    },
    addLibraryItem: (sectionId, bulletId) => {
      const current = recordRef.current;
      if (!current) return;
      void runWrite(() =>
        client.POST("/resumes/{resume_id}/items", {
          params: { path: { resume_id: current.id }, header: ifMatch() },
          body: { section_id: sectionId, item: { kind: "library_ref", bullet_id: bulletId } },
        }),
      ).then((ok) => {
        if (ok) void refreshBullets();
      });
    },
    addInlineItem: (sectionId, text) => {
      const current = recordRef.current;
      if (!current) return;
      void runWrite(() =>
        client.POST("/resumes/{resume_id}/items", {
          params: { path: { resume_id: current.id }, header: ifMatch() },
          body: { section_id: sectionId, item: { kind: "local", text } },
        }),
      );
    },
    removeItem: (itemId) => {
      const current = recordRef.current;
      if (!current) return;
      void runWrite(() =>
        client.POST("/resumes/{resume_id}/items/{item_id}/remove", {
          params: { path: { resume_id: current.id, item_id: itemId }, header: ifMatch() },
        }),
      ).then((ok) => {
        if (ok) void refreshBullets();
      });
    },
    reorderSections: (orderedSectionIds) => {
      const current = recordRef.current;
      if (!current) return;
      void runWrite(() =>
        client.POST("/resumes/{resume_id}/reorder", {
          params: { path: { resume_id: current.id }, header: ifMatch() },
          body: { section_order: orderedSectionIds },
        }),
      );
    },
    reorderItems: (sectionId, orderedItemIds) => {
      const current = recordRef.current;
      if (!current) return;
      void runWrite(() =>
        client.POST("/resumes/{resume_id}/reorder", {
          params: { path: { resume_id: current.id }, header: ifMatch() },
          body: { item_orders: { [sectionId]: orderedItemIds } },
        }),
      );
    },
    setTemplate: (templateId) => putUpdate({ template_id: templateId }),
    setTitle: (title) => putUpdate({ title }),
    setIdentityVariant: (variantId) => {
      const current = recordRef.current;
      if (!current) return;
      putUpdate({ header: { ...current.document.header, identity_variant_id: variantId } });
    },
    promoteItem: (itemId) => {
      const current = recordRef.current;
      if (!current) return;
      void runWrite(() =>
        client.POST("/resumes/{resume_id}/items/{item_id}/promote", {
          params: { path: { resume_id: current.id, item_id: itemId }, header: ifMatch() },
        }),
      ).then((ok) => {
        if (ok) void refreshBullets();
      });
    },
    exportPdf: async () => {
      const current = recordRef.current;
      if (!current) return null;
      const { data } = await client.POST("/resumes/{resume_id}/export", {
        params: { path: { resume_id: current.id } },
      });
      return data?.download_url ?? null;
    },
    finalizeResume: async () => {
      const current = recordRef.current;
      if (!current) return false;
      setWriteState({ status: "saving" });
      const {
        data,
        error: finalizeError,
        response,
      } = await client.POST("/resumes/{resume_id}/finalize", {
        params: { path: { resume_id: current.id } },
      });
      if (response.status === 409) {
        setWriteState({ status: "stale" });
        return false;
      }
      if (finalizeError || !data) {
        setWriteState({
          status: "error",
          message: extractProblem(finalizeError, FINALIZE_ERROR).message,
        });
        return false;
      }
      // Finalize returns a summary, not the record. Re-read the resume (now frozen
      // and read-only) and refresh bullets, whose "used in N" dropped the refs.
      const { data: refreshed } = await client.GET("/resumes/{resume_id}", {
        params: { path: { resume_id: current.id } },
      });
      if (refreshed) applyRecord(refreshed);
      await refreshBullets();
      setWriteState({ status: "idle" });
      return true;
    },
  };

  return {
    state: {
      load: loadState,
      write: writeState,
      record,
      bullets,
      variants,
      templates,
      scopePrompt,
      isReadOnly: record?.status === "finalized",
      previewKey,
    },
    actions,
  };
}

interface WriteResult {
  data?: ResumeRecord;
  error?: unknown;
  response: Response;
}

function indexById(bulletList: BulletpointRecord[]): Record<number, BulletpointRecord> {
  return bulletList.reduce<Record<number, BulletpointRecord>>((acc, bullet) => {
    acc[bullet.id] = bullet;
    return acc;
  }, {});
}
