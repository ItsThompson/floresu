import { useEffect, useRef, useState } from "react";
import { Maximize2 } from "lucide-react";

import { Modal } from "@/components/Modal";
import type { PdfRenderer } from "@/lib/renderPdf";

import { useResumePreview, type PreviewStatus } from "../hooks/useResumePreview";

const THUMBNAIL_SCALE = 0.6;
const EXPANDED_SCALE = 1.4;

interface PdfPreviewProps {
  previewKey: number;
  /** Fetch the ephemeral rendered PDF bytes (injected boundary to the API). */
  fetchPreview: () => Promise<Blob>;
  /** Render a PDF blob into a canvas (injected boundary to PDF.js). */
  renderPdf: PdfRenderer;
  /** Reports the effective preview status so the caller can block export on failure. */
  onStatusChange?: (status: PreviewStatus) => void;
}

/**
 * The live PDF preview: a clickable thumbnail that expands to a larger view. The
 * bytes are fetched (debounced) and rendered with PDF.js; both boundaries are
 * injected so the component is testable without the real library. A fetch or
 * render failure shows an error and reports `error` upward so export is blocked;
 * a stale image is never shown as current. The expand transition respects
 * reduced-motion (the modal fades only under `motion-safe`).
 *
 * The thumbnail is the one thing in the editor that genuinely floats: it is a
 * sheet of paper above the page, so it takes the reserved elevation. Nothing else
 * in this view carries a shadow except the dialogs.
 */
export function PdfPreview({
  previewKey,
  fetchPreview,
  renderPdf,
  onStatusChange,
}: PdfPreviewProps) {
  const { status, blob } = useResumePreview({ previewKey, fetchPreview });
  const [renderFailed, setRenderFailed] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const thumbnailRef = useRef<HTMLCanvasElement>(null);
  const expandedRef = useRef<HTMLCanvasElement>(null);

  const effectiveStatus: PreviewStatus = status === "error" || renderFailed ? "error" : status;

  useEffect(() => {
    onStatusChange?.(effectiveStatus);
  }, [effectiveStatus, onStatusChange]);

  useEffect(() => {
    setRenderFailed(false);
    if (status !== "ready" || !blob || !thumbnailRef.current) return;
    renderPdf(blob, thumbnailRef.current, THUMBNAIL_SCALE).catch(() => setRenderFailed(true));
  }, [status, blob, renderPdf]);

  useEffect(() => {
    if (!isExpanded || !blob || !expandedRef.current) return;
    renderPdf(blob, expandedRef.current, EXPANDED_SCALE).catch(() => setRenderFailed(true));
  }, [isExpanded, blob, renderPdf]);

  return (
    <aside aria-label="Resume preview" className="flex flex-col items-center gap-2">
      <h2 className="text-muted-foreground caption self-start">Preview</h2>

      {effectiveStatus === "loading" && (
        <p className="text-muted-foreground text-sm">Rendering preview…</p>
      )}

      {effectiveStatus === "error" && (
        <p role="alert" className="text-destructive text-sm">
          The preview failed to render. Fix the resume to export.
        </p>
      )}

      {effectiveStatus === "ready" && (
        <button
          type="button"
          onClick={() => setIsExpanded(true)}
          className="bg-card shadow-floating focus-visible:ring-ring/50 relative rounded-lg p-1 outline-none focus-visible:ring-[3px]"
        >
          <canvas ref={thumbnailRef} className="rounded-sm" />
          <span className="bg-muted text-muted-foreground caption absolute right-2 bottom-2 flex items-center gap-1 rounded-md px-1.5 py-0.5">
            <Maximize2 aria-hidden className="size-3" /> Click to enlarge
          </span>
        </button>
      )}

      <p className="text-muted-foreground mono-meta">Auto-updates ~0.5s after edits.</p>

      <Modal
        isOpen={isExpanded}
        onClose={() => setIsExpanded(false)}
        title="Resume preview"
        size="xl"
      >
        <div className="flex max-h-[70vh] justify-center overflow-auto">
          <canvas ref={expandedRef} />
        </div>
      </Modal>
    </aside>
  );
}
