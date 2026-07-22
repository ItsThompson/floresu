import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";

import { Modal } from "@/components/Modal";
import { Button } from "@/components/ui/button";
import { formatDayYear } from "@/lib/formatDate";
import { cn } from "@/lib/utils";

import type { PdfRenderer } from "../pdf/renderPdf";
import type { PublishedVersion } from "../types";
import { useResumeHistory } from "../hooks/useResumeHistory";

const EMPTY_STATE = "No published versions yet. Export or finalize to create one.";
const PDF_UNAVAILABLE = "This version's PDF is unavailable.";
const LIST_ERROR = "Could not load version history. Close and reopen to retry.";
const PDF_VIEW_SCALE = 1.2;

/** The version-list fetch lifecycle (loading, ready, or a recoverable error). */
type ListState =
  | { status: "loading" }
  | { status: "ready"; versions: PublishedVersion[] }
  | { status: "error" };

/**
 * The selected version's PDF lifecycle. `loading` covers minting the URL and
 * fetching the bytes; `ready` carries the fetched blob to render read-only; any
 * mint/fetch/render failure lands on `error`, which surfaces on the row so other
 * rows keep working and re-selecting re-mints a fresh URL.
 */
type Selection =
  | { revisionNo: number; status: "loading" }
  | { revisionNo: number; status: "ready"; blob: Blob }
  | { revisionNo: number; status: "error" };

interface HistoryDialogProps {
  isOpen: boolean;
  onClose: () => void;
  /** The resume whose published versions are listed. */
  resumeId: number;
  /** Render a PDF blob into a canvas (injected boundary to PDF.js). */
  renderPdf: PdfRenderer;
}

/**
 * The Revision History modal: lists a resume's published versions newest-first
 * and renders the selected version's stored PDF read-only. The list and the
 * per-version presigned URL come from `useResumeHistory`; the browser fetches the
 * PDF bytes straight from R2 via that URL (never proxied) and renders them through
 * the injected boundary. Every listed version is view-only: there is no edit
 * affordance for a past version.
 */
export function HistoryDialog({ isOpen, onClose, resumeId, renderPdf }: HistoryDialogProps) {
  const { list, open } = useResumeHistory(resumeId);
  const [listState, setListState] = useState<ListState>({ status: "loading" });
  const [selection, setSelection] = useState<Selection | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setListState({ status: "loading" });
    setSelection(null);
    list()
      .then((versions) => {
        if (!cancelled) setListState({ status: "ready", versions });
      })
      .catch(() => {
        if (!cancelled) setListState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, list]);

  const selectVersion = useCallback(
    async (revisionNo: number) => {
      setSelection({ revisionNo, status: "loading" });
      try {
        const url = await open(revisionNo);
        const response = await fetch(url);
        if (!response.ok) throw new Error(PDF_UNAVAILABLE);
        const blob = await response.blob();
        setSelection((current) =>
          current?.revisionNo === revisionNo ? { revisionNo, status: "ready", blob } : current,
        );
      } catch {
        setSelection((current) =>
          current?.revisionNo === revisionNo ? { revisionNo, status: "error" } : current,
        );
      }
    },
    [open],
  );

  useEffect(() => {
    if (selection?.status !== "ready" || !canvasRef.current) return;
    const { revisionNo, blob } = selection;
    let cancelled = false;
    renderPdf(blob, canvasRef.current, PDF_VIEW_SCALE).catch(() => {
      if (cancelled) return;
      setSelection((current) =>
        current?.revisionNo === revisionNo && current.status === "ready"
          ? { revisionNo, status: "error" }
          : current,
      );
    });
    return () => {
      cancelled = true;
    };
  }, [selection, renderPdf]);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Version history" size="xl">
      {listState.status === "loading" && (
        <p role="status" className="text-muted-foreground flex items-center gap-2 text-sm">
          <Loader2 aria-hidden className="size-4 animate-spin" /> Loading versions…
        </p>
      )}

      {listState.status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          {LIST_ERROR}
        </p>
      )}

      {listState.status === "ready" && listState.versions.length === 0 && (
        <p className="text-muted-foreground text-sm">{EMPTY_STATE}</p>
      )}

      {listState.status === "ready" && listState.versions.length > 0 && (
        <div className="flex flex-col gap-4 md:flex-row">
          <ul className="flex max-h-[60vh] flex-col gap-2 overflow-auto md:w-56 md:shrink-0">
            {listState.versions.map((version) => {
              const isSelected = selection?.revisionNo === version.revision_no;
              return (
                <li key={version.revision_no}>
                  <button
                    type="button"
                    onClick={() => void selectVersion(version.revision_no)}
                    aria-current={isSelected ? "true" : undefined}
                    className={cn(
                      "flex w-full flex-col items-start gap-0.5 rounded-md border px-3 py-2 text-left text-sm",
                      isSelected ? "border-primary bg-accent" : "hover:bg-accent",
                    )}
                  >
                    <span className="font-medium">Revision {version.revision_no}</span>
                    <span className="text-muted-foreground text-xs">
                      {formatDayYear(version.created_at)}
                    </span>
                  </button>
                  {isSelected && selection.status === "error" && (
                    <p role="alert" className="text-destructive mt-1 px-1 text-xs">
                      {PDF_UNAVAILABLE}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>

          <div className="min-h-[240px] flex-1">
            {(selection === null || selection.status === "error") && (
              <p className="text-muted-foreground text-sm">Select a version to view its PDF.</p>
            )}
            {selection?.status === "loading" && (
              <p role="status" className="text-muted-foreground flex items-center gap-2 text-sm">
                <Loader2 aria-hidden className="size-4 animate-spin" /> Loading version…
              </p>
            )}
            {selection?.status === "ready" && (
              <div className="flex max-h-[60vh] justify-center overflow-auto rounded-md border p-2">
                <canvas ref={canvasRef} aria-label={`Revision ${selection.revisionNo} PDF`} />
              </div>
            )}
          </div>
        </div>
      )}

      <div className="flex justify-end">
        <Button variant="outline" onClick={onClose}>
          Close
        </Button>
      </div>
    </Modal>
  );
}
