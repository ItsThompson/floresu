import type { FormEvent } from "react";

import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";

import type { LibraryToolbarProps } from "../types";

// The search field copies the calm field shape of
// `frontend/src/components/FormInputField`.
const SEARCH_FIELD_CLASS =
  "border-input bg-card text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 h-9 min-w-0 flex-1 rounded-md border px-3 text-sm outline-none focus-visible:ring-[3px]";

/**
 * The Library header controls: the hybrid-search field with its submit, a clear
 * control shown only while a search is active, and the new-bullet action. The
 * search field is a real form so Enter submits; submitting an empty query is a
 * no-op the hook resolves to the browse (no results) state.
 */
export function LibraryToolbar({
  query,
  isSearching,
  hasActiveSearch,
  onQueryChange,
  onSubmit,
  onClear,
  onNewBullet,
}: LibraryToolbarProps) {
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit();
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      <form role="search" onSubmit={handleSubmit} className="flex flex-1 items-center gap-2">
        <input
          type="search"
          aria-label="Search experience"
          placeholder="Search your worklog and bullets"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          className={SEARCH_FIELD_CLASS}
        />
        <Button type="submit" disabled={isSearching}>
          {isSearching ? "Searching…" : "Search"}
        </Button>
        {hasActiveSearch && (
          <Button type="button" variant="ghost" onClick={onClear}>
            Clear
          </Button>
        )}
      </form>
      <Button type="button" variant="ghost" onClick={onNewBullet}>
        <Plus aria-hidden />
        New bullet
      </Button>
    </div>
  );
}
