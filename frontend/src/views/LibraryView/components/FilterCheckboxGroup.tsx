import type { FilterCheckboxGroupProps } from "../types";

const slug = (legend: string): string => legend.toLowerCase().replace(/[^a-z0-9]+/g, "-");

/**
 * A labeled group of checkboxes for a multi-select filter (source kinds, tags,
 * sources, or worklog links). Generic over string or numeric option values so
 * callers pass their ids directly with no stringify dance. Purely presentational:
 * it reports each toggle and holds no selection state of its own.
 */
export function FilterCheckboxGroup<T extends string | number>({
  legend,
  options,
  selected,
  onToggle,
}: FilterCheckboxGroupProps<T>) {
  if (options.length === 0) return null;
  const groupId = slug(legend);

  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="text-foreground text-sm font-medium">{legend}</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {options.map((option) => {
          const inputId = `${groupId}-${String(option.value)}`;
          return (
            <label key={inputId} htmlFor={inputId} className="flex items-center gap-1.5 text-sm">
              <input
                id={inputId}
                type="checkbox"
                checked={selected.includes(option.value)}
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
