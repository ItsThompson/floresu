import { useState } from "react";
import { Download, History, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { ExportState } from "@/lib/asyncState";

import type { ResumeRecord, TemplateInfo } from "../types";
import { TemplateSelect } from "./TemplateSelect";

interface EditorTopBarProps {
  record: ResumeRecord;
  templates: TemplateInfo[];
  isReadOnly: boolean;
  /** Export is blocked while the preview is in an error state. */
  canExport: boolean;
  onSetTitle: (title: string) => void;
  onSetTemplate: (templateId: string) => void;
  onExport: () => Promise<string | null>;
  onRefresh: () => void;
  /** Open the finalize confirm gate (application resumes only). */
  onRequestFinalize: () => void;
  /** Open the revision-history dialog (lists this resume's published versions). */
  onRequestHistory: () => void;
}

/**
 * The editor header: the editable title, the kind/status line, the template
 * selector, and the actions (export, refresh, finalize, and history).
 * Export renders and persists a PDF and surfaces a download link; finalize opens
 * a confirm gate (rendered by the orchestrator) and is shown only for an editable
 * application resume. History opens the revision dialog, which lists the resume's
 * published versions and serves each stored PDF read-only.
 */
export function EditorTopBar({
  record,
  templates,
  isReadOnly,
  canExport,
  onSetTitle,
  onSetTemplate,
  onExport,
  onRefresh,
  onRequestFinalize,
  onRequestHistory,
}: EditorTopBarProps) {
  const [title, setTitle] = useState(record.title);
  const [lastTitle, setLastTitle] = useState(record.title);
  if (record.title !== lastTitle) {
    setLastTitle(record.title);
    setTitle(record.title);
  }

  const [exportState, setExportState] = useState<ExportState>({ status: "idle" });

  const doExport = async () => {
    setExportState({ status: "saving" });
    const url = await onExport();
    if (!url) {
      setExportState({
        status: "error",
        message: "Export failed. Fix any preview error and try again.",
      });
      return;
    }
    setExportState({ status: "done", url });
    window.open(url, "_blank", "noopener");
  };

  return (
    <header className="flex flex-col gap-3 border-b pb-4">
      <div className="flex items-center gap-3">
        <input
          aria-label="Resume title"
          value={title}
          disabled={isReadOnly}
          onChange={(event) => setTitle(event.target.value)}
          onBlur={() => title.trim() && title !== record.title && onSetTitle(title.trim())}
          className="flex-1 rounded-md border-transparent bg-transparent text-xl font-semibold outline-none focus-visible:border-input focus-visible:border disabled:opacity-70"
        />
        <span className="text-muted-foreground text-sm capitalize">
          {record.kind} · {record.status}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <TemplateSelect
          templates={templates}
          selectedTemplateId={record.document.template_id}
          isReadOnly={isReadOnly}
          onChange={onSetTemplate}
        />
        <Button
          variant="outline"
          size="sm"
          onClick={() => void doExport()}
          disabled={!canExport || exportState.status === "saving"}
        >
          <Download aria-hidden /> Export
        </Button>
        <Button variant="ghost" size="sm" onClick={onRefresh}>
          <RefreshCw aria-hidden /> Refresh
        </Button>
        <Button variant="ghost" size="sm" onClick={onRequestHistory}>
          <History aria-hidden /> History
        </Button>
        {record.kind === "application" && !isReadOnly && (
          <Button variant="default" size="sm" onClick={onRequestFinalize}>
            Finalize
          </Button>
        )}
      </div>

      {exportState.status === "done" && (
        <a
          href={exportState.url}
          target="_blank"
          rel="noopener"
          className="text-primary text-sm underline"
        >
          Download exported PDF
        </a>
      )}
      {exportState.status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          {exportState.message}
        </p>
      )}
    </header>
  );
}
