import { SEARCH_LAYER_OPTIONS, SOURCE_KIND_OPTIONS } from "../constants";
import type { SearchFiltersProps } from "../types";
import { toggleValue } from "@/lib/toggleValue";
import { FilterCheckboxGroup } from "./FilterCheckboxGroup";

// The layer select and the two date fields share the calm field shape of
// `frontend/src/components/FormInputField`.
const FIELD_CLASS =
  "border-input bg-card text-foreground focus-visible:border-ring focus-visible:ring-ring/50 h-9 rounded-md border px-3 text-sm outline-none focus-visible:ring-[3px]";

/**
 * The search filter panel: source kind, source, and tag multi-selects plus a
 * layer selector and a date range. Filters narrow the corpus before retrieval
 * and apply together; each control reports its change up to the hook, which owns
 * the filter state. Presentational only.
 */
export function SearchFilters({ sources, tags, filters, onChange }: SearchFiltersProps) {
  return (
    <div className="bg-card border-border flex flex-col gap-3 rounded-md border p-3">
      <FilterCheckboxGroup
        legend="Kind"
        variant="chip"
        options={SOURCE_KIND_OPTIONS}
        selected={filters.kinds}
        onToggle={(kind) => onChange({ kinds: toggleValue(filters.kinds, kind) })}
      />

      <FilterCheckboxGroup
        legend="Source"
        variant="chip"
        options={sources.map((source) => ({ value: source.id, label: source.display_label }))}
        selected={filters.sourceIds}
        onToggle={(id) => onChange({ sourceIds: toggleValue(filters.sourceIds, id) })}
      />

      <FilterCheckboxGroup
        legend="Tag"
        variant="chip"
        options={tags.map((tag) => ({ value: tag.label, label: tag.label }))}
        selected={filters.tags}
        onToggle={(label) => onChange({ tags: toggleValue(filters.tags, label) })}
      />

      <div className="flex flex-wrap items-end gap-4">
        <label className="caption text-foreground flex flex-col gap-1.5">
          Layer
          <select
            value={filters.layer}
            onChange={(event) => onChange({ layer: event.target.value as typeof filters.layer })}
            className={FIELD_CLASS}
          >
            {SEARCH_LAYER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="caption text-foreground flex flex-col gap-1.5">
          From
          <input
            type="date"
            aria-label="From date"
            value={filters.dateFrom}
            onChange={(event) => onChange({ dateFrom: event.target.value })}
            className={FIELD_CLASS}
          />
        </label>

        <label className="caption text-foreground flex flex-col gap-1.5">
          To
          <input
            type="date"
            aria-label="To date"
            value={filters.dateTo}
            onChange={(event) => onChange({ dateTo: event.target.value })}
            className={FIELD_CLASS}
          />
        </label>
      </div>
    </div>
  );
}
