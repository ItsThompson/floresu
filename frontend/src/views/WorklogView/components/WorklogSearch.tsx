import { SearchResults } from "@/components/SearchResults";
import { Button } from "@/components/ui/button";

import type { WorklogSearchActions, WorklogSearchViewState } from "../types";

interface WorklogSearchProps {
  state: WorklogSearchViewState;
  actions: WorklogSearchActions;
}

// The same field shape as `frontend/src/components/FormInputField/`: the card
// fill on the input border, with the bloom focus ring as the loud moment.
const FIELD_CLASS =
  "border-input bg-card text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 h-9 flex-1 rounded-md border px-3 text-sm outline-none focus-visible:ring-[3px]";

/**
 * The embedded hybrid-search field and its results. A submit runs the search
 * across worklog and bullets under the page's active filters; the shared result
 * view renders the fused ranked mix beside the same hits grouped by source. An
 * empty query renders nothing.
 */
export function WorklogSearch({ state, actions }: WorklogSearchProps) {
  const { query, search } = state;
  return (
    <div className="flex flex-col gap-3">
      <form
        role="search"
        className="flex items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void actions.submit();
        }}
      >
        <input
          type="search"
          aria-label="Search worklog and bullets"
          placeholder="Search your experience…"
          value={query}
          onChange={(event) => actions.setQuery(event.target.value)}
          className={FIELD_CLASS}
        />
        <Button type="submit" size="sm" disabled={search.status === "searching"}>
          {search.status === "searching" ? "Searching…" : "Search"}
        </Button>
        {search.status !== "idle" && (
          <Button type="button" variant="ghost" size="sm" onClick={actions.clear}>
            Clear
          </Button>
        )}
      </form>

      {search.status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          {search.message}
        </p>
      )}

      {search.status === "results" && <SearchResults result={search.result} />}
    </div>
  );
}
