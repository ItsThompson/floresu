import type { SourceSummary, WorklogFilters } from "../types";

interface WorklogFiltersProps {
  sources: SourceSummary[];
  tagOptions: string[];
  filters: WorklogFilters;
  onSourceChange: (sourceId: number | null) => void;
  onTagChange: (tag: string | null) => void;
  onDateRangeChange: (from: string | null, to: string | null) => void;
  onClear: () => void;
}

const SELECT_CLASS =
  "border-input bg-background h-9 rounded-md border px-2 text-sm";
const DATE_CLASS = "border-input bg-background h-9 rounded-md border px-2 text-sm";

/**
 * Source, tag, and date-range filters for the timeline. Each is a controlled
 * input that emits its change; the combined narrowing happens upstream, so every
 * active filter applies together.
 */
export function WorklogFilters({
  sources,
  tagOptions,
  filters,
  onSourceChange,
  onTagChange,
  onDateRangeChange,
  onClear,
}: WorklogFiltersProps) {
  const hasActiveFilter =
    filters.sourceId !== null ||
    filters.tag !== null ||
    filters.dateFrom !== null ||
    filters.dateTo !== null;

  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1 text-xs font-medium">
        Source
        <select
          className={SELECT_CLASS}
          value={filters.sourceId ?? ""}
          onChange={(event) => onSourceChange(event.target.value === "" ? null : Number(event.target.value))}
        >
          <option value="">All sources</option>
          {sources.map((source) => (
            <option key={source.id} value={source.id}>
              {source.display_label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs font-medium">
        Tag
        <select
          className={SELECT_CLASS}
          value={filters.tag ?? ""}
          onChange={(event) => onTagChange(event.target.value === "" ? null : event.target.value)}
        >
          <option value="">All tags</option>
          {tagOptions.map((tag) => (
            <option key={tag} value={tag}>
              #{tag}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs font-medium">
        From
        <input
          type="date"
          className={DATE_CLASS}
          value={filters.dateFrom ?? ""}
          onChange={(event) => onDateRangeChange(event.target.value || null, filters.dateTo)}
        />
      </label>

      <label className="flex flex-col gap-1 text-xs font-medium">
        To
        <input
          type="date"
          className={DATE_CLASS}
          value={filters.dateTo ?? ""}
          onChange={(event) => onDateRangeChange(filters.dateFrom, event.target.value || null)}
        />
      </label>

      {hasActiveFilter && (
        <button
          type="button"
          onClick={onClear}
          className="text-muted-foreground h-9 text-sm hover:underline"
        >
          Clear
        </button>
      )}
    </div>
  );
}
