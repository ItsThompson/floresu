import { useCallback, useState } from "react";
import { Link, useParams } from "react-router";

import { useSessionClient } from "@/api";
import { RESUMES_PATH } from "@/lib/resumePaths";

import { EditorTopBar } from "./components/EditorTopBar";
import { PdfPreview } from "./components/PdfPreview";
import { ScopeDialog } from "./components/ScopeDialog";
import { SectionForm } from "./components/SectionForm";
import { StaleSaveDialog } from "./components/StaleSaveDialog";
import { useResumeEditor } from "./hooks/useResumeEditor";
import type { PreviewStatus } from "./hooks/useResumePreview";
import { renderPdfToCanvas } from "./pdf/renderPdf";

/**
 * The three-column resume editor: the section form on the left, the live PDF
 * preview on the right, and the copy-on-write scope prompt over the top. It is
 * composition only: `useResumeEditor` owns the load and every write (each guarded
 * by the revision), and the preview fetch/render boundaries are built here and
 * injected into `PdfPreview`.
 */
export function ResumeEditorView() {
  const params = useParams();
  const resumeId = Number(params.resumeId);
  const client = useSessionClient();
  const { state, actions } = useResumeEditor(resumeId);
  const [previewStatus, setPreviewStatus] = useState<PreviewStatus>("loading");
  const [refreshNonce, setRefreshNonce] = useState(0);

  const fetchPreview = useCallback(async (): Promise<Blob> => {
    const { data, error } = await client.POST("/resumes/{resume_id}/preview", {
      params: { path: { resume_id: resumeId } },
      body: {},
      parseAs: "blob",
    });
    if (error || !data) throw new Error("Preview render failed.");
    return data as Blob;
  }, [client, resumeId]);

  if (Number.isNaN(resumeId) || state.status === "error") {
    return (
      <section className="mx-auto flex w-full max-w-[860px] flex-col gap-4 p-8">
        <p role="alert" className="text-destructive text-sm">
          {state.error ?? "This resume could not be found."}
        </p>
        <Link to={RESUMES_PATH} className="text-primary text-sm underline">
          Back to resumes
        </Link>
      </section>
    );
  }

  if (state.status === "loading" || !state.record) {
    return <p className="text-muted-foreground p-8 text-sm">Loading resume…</p>;
  }

  return (
    <section className="flex w-full flex-col gap-4 p-6">
      <Link to={RESUMES_PATH} className="text-muted-foreground text-sm hover:underline">
        ← All resumes
      </Link>

      <div className="flex flex-col gap-6 lg:flex-row">
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <EditorTopBar
            record={state.record}
            templates={state.templates}
            isReadOnly={state.isReadOnly}
            canExport={previewStatus !== "error"}
            onSetTitle={actions.setTitle}
            onSetTemplate={actions.setTemplate}
            onExport={actions.exportPdf}
            onRefresh={() => setRefreshNonce((nonce) => nonce + 1)}
          />

          {state.saveError && (
            <p role="alert" className="text-destructive text-sm">
              {state.saveError}
            </p>
          )}

          <SectionForm
            record={state.record}
            bulletsById={state.bullets}
            allBullets={Object.values(state.bullets)}
            variants={state.variants}
            isReadOnly={state.isReadOnly}
            actions={actions}
          />
        </div>

        <div className="w-full shrink-0 lg:w-80">
          <div className="lg:sticky lg:top-6">
            <PdfPreview
              previewKey={state.previewKey + refreshNonce}
              fetchPreview={fetchPreview}
              renderPdf={renderPdfToCanvas}
              onStatusChange={setPreviewStatus}
            />
          </div>
        </div>
      </div>

      <ScopeDialog
        context={state.scopePrompt}
        onApply={actions.resolveScope}
        onCancel={actions.cancelScope}
      />
      <StaleSaveDialog isOpen={state.isStale} onReload={actions.reload} onDismiss={actions.dismissStale} />
    </section>
  );
}
