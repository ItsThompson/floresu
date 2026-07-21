import { Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

import type { ContextualWorklog } from "../hooks/useContextualWorklog";
import { AddWorklogEntryForm } from "./AddWorklogEntryForm";
import { WorklogMonthGroup } from "./WorklogMonthGroup";

interface ContextualWorklogPanelProps {
  worklog: ContextualWorklog;
}

/**
 * Column three of the source detail: this source's worklog, grouped by month,
 * with a quick add that pre-attaches the new entry to the source. Adding closes
 * the form on success (the entry count grows), so the panel reflects the write.
 */
export function ContextualWorklogPanel({ worklog }: ContextualWorklogPanelProps) {
  const [isAdding, setIsAdding] = useState(false);
  const [countAtOpen, setCountAtOpen] = useState<number | null>(null);

  // Close the add form once the entry count grows past what it was when opened.
  useEffect(() => {
    if (isAdding && countAtOpen !== null && worklog.entryCount > countAtOpen) {
      setIsAdding(false);
      setCountAtOpen(null);
    }
  }, [isAdding, countAtOpen, worklog.entryCount]);

  const openForm = () => {
    setCountAtOpen(worklog.entryCount);
    setIsAdding(true);
  };

  return (
    <section aria-label="Work log" className="flex flex-col gap-3">
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-tight">Work Log</h2>
        {!isAdding && (
          <Button type="button" size="sm" variant="outline" onClick={openForm}>
            <Plus className="size-3.5" /> Add entry
          </Button>
        )}
      </header>

      {isAdding && (
        <AddWorklogEntryForm
          isAdding={worklog.isAdding}
          error={worklog.addError}
          onAdd={worklog.addEntry}
          onCancel={() => setIsAdding(false)}
        />
      )}

      {worklog.status === "loading" && (
        <p className="text-muted-foreground text-sm">Loading entries…</p>
      )}
      {worklog.status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          Could not load entries.
        </p>
      )}
      {worklog.status === "ready" && worklog.months.length === 0 && (
        <p className="text-muted-foreground text-sm">No entries for this source yet.</p>
      )}
      {worklog.status === "ready" && worklog.months.length > 0 && (
        <div className="flex flex-col gap-4">
          {worklog.months.map((month) => (
            <WorklogMonthGroup key={month.key} month={month} />
          ))}
        </div>
      )}
    </section>
  );
}
