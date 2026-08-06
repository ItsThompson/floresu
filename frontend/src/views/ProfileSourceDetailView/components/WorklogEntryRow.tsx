import { TagPill } from "@/components/TagPill";
import { formatDay } from "@/lib/formatDate";

import type { WorklogSummary } from "../types";

interface WorklogEntryRowProps {
  entry: WorklogSummary;
}

/**
 * One contextual worklog row: its day, title, an optional description, and its
 * tag pills. This is a compact display for the source-detail side panel; the full
 * timeline with filters lives in the Worklog view.
 */
export function WorklogEntryRow({ entry }: WorklogEntryRowProps) {
  return (
    <li className="flex flex-col gap-1 py-1.5">
      <div className="flex items-baseline gap-2">
        <time dateTime={entry.entry_date} className="text-muted-foreground mono-meta shrink-0">
          {formatDay(entry.entry_date)}
        </time>
        <span className="text-foreground text-sm font-medium">{entry.title}</span>
      </div>
      {entry.description && (
        <p className="text-muted-foreground caption line-clamp-2">{entry.description}</p>
      )}
      {entry.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {entry.tags.map((tag) => (
            <TagPill key={tag} label={tag} />
          ))}
        </div>
      )}
    </li>
  );
}
