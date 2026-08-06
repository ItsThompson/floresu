import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { SourceSummary, WorklogFilterValues } from "../types";

interface WorklogFiltersProps {
  sources: SourceSummary[];
  tagOptions: string[];
  filters: WorklogFilterValues;
  onSourceChange: (sourceId: number | null) => void;
  onTagChange: (tag: string | null) => void;
  onDateRangeChange: (from: string | null, to: string | null) => void;
  onClear: () => void;
}

// The chips reuse the tag pill's shape. An active chip is the only loud moment in
// the bar: the accent tint carries its own deeper coral text, which clears the AA
// floor where the action coral does not.
//
// The controls inside drop their own outline, so the ring lives on the pill: the
// chip is what the user perceives as the control, and a square outline inside a
// full-radius pill reads as a mistake. Focus is never left unindicated.
const CHIP_BASE =
  "caption focus-within:border-ring focus-within:ring-ring/50 inline-flex items-center gap-2 rounded-full border px-3 py-1.5 focus-within:ring-[3px]";
const CHIP_IDLE = "border-input bg-card text-muted-foreground";
const CHIP_ACTIVE = "bg-accent text-accent-foreground border-transparent";

const chipClass = (isActive: boolean) => cn(CHIP_BASE, isActive ? CHIP_ACTIVE : CHIP_IDLE);

// The control inherits the chip's color, so an active chip reads as one pill
// rather than a tinted frame around unrelated text.
const SELECT_CLASS = "cursor-pointer bg-transparent outline-none";
const DATE_CLASS = "bg-transparent outline-none";

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
    <div className="flex flex-wrap items-center gap-2">
      <label className={chipClass(filters.sourceId !== null)}>
        Source
        <select
          className={SELECT_CLASS}
          value={filters.sourceId ?? ""}
          onChange={(event) =>
            onSourceChange(event.target.value === "" ? null : Number(event.target.value))
          }
        >
          <option value="">All sources</option>
          {sources.map((source) => (
            <option key={source.id} value={source.id}>
              {source.display_label}
            </option>
          ))}
        </select>
      </label>

      <label className={chipClass(filters.tag !== null)}>
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

      <label className={chipClass(filters.dateFrom !== null)}>
        From
        <input
          type="date"
          className={DATE_CLASS}
          value={filters.dateFrom ?? ""}
          onChange={(event) => onDateRangeChange(event.target.value || null, filters.dateTo)}
        />
      </label>

      <label className={chipClass(filters.dateTo !== null)}>
        To
        <input
          type="date"
          className={DATE_CLASS}
          value={filters.dateTo ?? ""}
          onChange={(event) => onDateRangeChange(filters.dateFrom, event.target.value || null)}
        />
      </label>

      {hasActiveFilter && (
        <Button type="button" variant="ghost" size="sm" onClick={onClear}>
          Clear
        </Button>
      )}
    </div>
  );
}
