import { Link } from "react-router";

import { Button } from "@/components/ui/button";

import { libraryBulletHref, sourceDetailHref } from "../constants";
import type { ResolvedHit } from "../types";
import type { WorklogSearchActions, WorklogSearchState } from "../hooks/useWorklogSearch";

interface WorklogSearchProps {
  state: WorklogSearchState;
  actions: WorklogSearchActions;
}

const KIND_LABEL: Record<ResolvedHit["type"], string> = {
  worklog: "Worklog",
  bullet: "Bullet",
  source: "Source",
};

/**
 * The embedded hybrid-search field and its ranked results. A submit runs the
 * search across worklog and bullets; the fused mix renders in rank order.
 * Bullets and sources link to where they live; worklog hits are already on this
 * page. An empty query renders nothing.
 */
export function WorklogSearch({ state, actions }: WorklogSearchProps) {
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
          value={state.query}
          onChange={(event) => actions.setQuery(event.target.value)}
          className="border-input bg-background h-9 flex-1 rounded-md border px-3 text-sm"
        />
        <Button type="submit" size="sm" disabled={state.status === "searching"}>
          {state.status === "searching" ? "Searching…" : "Search"}
        </Button>
        {state.hasSearched && (
          <Button type="button" variant="ghost" size="sm" onClick={actions.clear}>
            Clear
          </Button>
        )}
      </form>

      {state.notices.map((notice) => (
        <p key={notice.code} role="status" className="text-muted-foreground text-xs">
          {notice.message}
        </p>
      ))}

      {state.status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          Search is unavailable right now.
        </p>
      )}

      {state.hasSearched && state.status === "idle" && state.results.length === 0 && (
        <p className="text-muted-foreground text-sm">No matches.</p>
      )}

      {state.results.length > 0 && (
        <ul aria-label="Search results" className="divide-border flex flex-col divide-y rounded-md border">
          {state.results.map((hit) => (
            <li key={`${hit.type}-${hit.id}`} className="flex items-center gap-3 px-3 py-2 text-sm">
              <span className="text-muted-foreground w-16 shrink-0 text-xs font-medium uppercase">
                {KIND_LABEL[hit.type]}
              </span>
              <span className="min-w-0 flex-1 truncate">
                {hit.type === "bullet" ? (
                  <Link to={libraryBulletHref(hit.id)} className="text-primary hover:underline">
                    {hit.label}
                  </Link>
                ) : hit.type === "source" ? (
                  <Link to={sourceDetailHref(hit.id)} className="text-primary hover:underline">
                    {hit.label}
                  </Link>
                ) : (
                  hit.label
                )}
              </span>
              {hit.detail && <span className="text-muted-foreground shrink-0 text-xs">{hit.detail}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
