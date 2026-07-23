import { Link } from "react-router";

import { sourceDetailHref } from "../constants";
import { formatDayLabel } from "../dateFormat";
import { sourceLabel } from "../sourceLabel";
import type { SourceSummary, WorklogSummary } from "../types";
import { EntryOverflowMenu } from "./EntryOverflowMenu";
import { TagPill } from "./TagPill";

interface WorklogRowProps {
  entry: WorklogSummary;
  sources: SourceSummary[];
  onEdit: (entryId: number) => void;
  onArchive: (entryId: number) => void;
}

/**
 * One timeline entry: the day, the title, its attached sources as links, and its
 * tag pills, with the overflow menu (edit, archive, derived bullets) on the
 * right. Purely presentational: it emits intent through its callbacks.
 */
export function WorklogRow({ entry, sources, onEdit, onArchive }: WorklogRowProps) {
  return (
    <li className="flex items-start gap-4 py-3">
      <time dateTime={entry.entry_date} className="text-muted-foreground w-16 shrink-0 pt-0.5 text-sm">
        {formatDayLabel(entry.entry_date)}
      </time>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="font-medium">{entry.title}</p>
        {(entry.source_ids.length > 0 || entry.tags.length > 0) && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {entry.source_ids.map((sourceId) => (
              <Link
                key={sourceId}
                to={sourceDetailHref(sourceId)}
                className="text-primary hover:underline"
              >
                @{sourceLabel(sources, sourceId)}
              </Link>
            ))}
            {entry.tags.map((tag) => (
              <TagPill key={tag} label={tag} />
            ))}
          </div>
        )}
      </div>

      <EntryOverflowMenu
        entryId={entry.id}
        entryTitle={entry.title}
        onEdit={() => onEdit(entry.id)}
        onArchive={() => onArchive(entry.id)}
      />
    </li>
  );
}
