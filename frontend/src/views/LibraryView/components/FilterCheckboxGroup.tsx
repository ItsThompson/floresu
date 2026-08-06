import { cn } from "@/lib/utils";

import type { FilterCheckboxGroupProps, FilterOptionVariant } from "../types";

const slug = (legend: string): string => legend.toLowerCase().replace(/[^a-z0-9]+/g, "-");

/**
 * Option styling per variant. A `chip` is the filter pill: checked, it takes the
 * accent fill, the one loud moment in an otherwise calm panel. A `checkbox` row
 * stays neutral in both states, because the bullet form's provenance links are
 * form content and an accent fill there would read as an action.
 */
const OPTION_CLASS: Record<
  FilterOptionVariant,
  { base: string; checked: string; unchecked: string }
> = {
  checkbox: { base: "text-sm", checked: "", unchecked: "" },
  chip: {
    base: "caption rounded-full border px-2.5 py-1",
    checked: "bg-accent text-accent-foreground border-accent",
    unchecked: "bg-card border-input text-muted-foreground",
  },
};

/**
 * A labeled group of checkboxes for a multi-select filter (source kinds, tags,
 * sources, or worklog links). Generic over string or numeric option values so
 * callers pass their ids directly with no stringify dance. Purely presentational:
 * it reports each toggle and holds no selection state of its own. The real
 * checkbox stays in the pill so the control keeps its role and its label.
 */
export function FilterCheckboxGroup<T extends string | number>({
  legend,
  options,
  selected,
  onToggle,
  variant = "checkbox",
}: FilterCheckboxGroupProps<T>) {
  if (options.length === 0) return null;
  const groupId = slug(legend);
  const optionClass = OPTION_CLASS[variant];

  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="text-foreground caption">{legend}</legend>
      <div className="flex flex-wrap gap-x-3 gap-y-1.5">
        {options.map((option) => {
          const inputId = `${groupId}-${String(option.value)}`;
          const isChecked = selected.includes(option.value);
          return (
            <label
              key={inputId}
              htmlFor={inputId}
              className={cn(
                "flex items-center gap-1.5",
                optionClass.base,
                isChecked ? optionClass.checked : optionClass.unchecked,
              )}
            >
              <input
                id={inputId}
                type="checkbox"
                checked={isChecked}
                onChange={() => onToggle(option.value)}
                className="size-4"
              />
              {option.label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
