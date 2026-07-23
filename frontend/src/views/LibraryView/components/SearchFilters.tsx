import { SEARCH_LAYER_OPTIONS, SOURCE_KIND_OPTIONS } from "../constants";
import type { SearchFiltersProps } from "../types";
import { toggleValue } from "@/lib/toggleValue";
import { FilterCheckboxGroup } from "./FilterCheckboxGroup";

/**
 * The search filter panel: source kind, source, and tag multi-selects plus a
 * layer selector and a date range. Filters narrow the corpus before retrieval
 * and apply together; each control reports its change up to the hook, which owns
 * the filter state. Presentational only.
 */
export function SearchFilters({ sources, tags, filters, onChange }: SearchFiltersProps) {
  return (
    <div className="border-border flex flex-col gap-3 rounded-md border p-3">
      <FilterCheckboxGroup
        legend="Kind"
        options={SOURCE_KIND_OPTIONS}
        selected={filters.kinds}
        onToggle={(kind) => onChange({ kinds: toggleValue(filters.kinds, kind) })}
      />

      <FilterCheckboxGroup
        legend="Source"
        options={sources.map((source) => ({ value: source.id, label: source.display_label }))}
        selected={filters.sourceIds}
        onToggle={(id) => onChange({ sourceIds: toggleValue(filters.sourceIds, id) })}
      />

      <FilterCheckboxGroup
        legend="Tag"
        options={tags.map((tag) => ({ value: tag.label, label: tag.label }))}
        selected={filters.tags}
        onToggle={(label) => onChange({ tags: toggleValue(filters.tags, label) })}
      />

      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Layer
          <select
            value={filters.layer}
            onChange={(event) => onChange({ layer: event.target.value as typeof filters.layer })}
            className="border-input bg-background h-9 rounded-md border px-3 text-sm"
          >
            {SEARCH_LAYER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5 text-sm font-medium">
          From
          <input
            type="date"
            aria-label="From date"
            value={filters.dateFrom}
            onChange={(event) => onChange({ dateFrom: event.target.value })}
            className="border-input bg-background h-9 rounded-md border px-3 text-sm"
          />
        </label>

        <label className="flex flex-col gap-1.5 text-sm font-medium">
          To
          <input
            type="date"
            aria-label="To date"
            value={filters.dateTo}
            onChange={(event) => onChange({ dateTo: event.target.value })}
            className="border-input bg-background h-9 rounded-md border px-3 text-sm"
          />
        </label>
      </div>
    </div>
  );
}
