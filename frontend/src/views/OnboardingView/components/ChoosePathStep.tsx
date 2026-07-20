import type { ChoosePathStepProps } from "../types";

/**
 * The cold-start choice: start manually or connect an agent. Either card is an
 * action (one finishes onboarding, the other advances the wizard), not a link to
 * a URL, so both are buttons. The copy states plainly that Floresu parses
 * nothing, and that both paths remain available later.
 */
export function ChoosePathStep({ onChooseManual, onChooseConnect, isBusy }: ChoosePathStepProps) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">How do you want to start?</h1>
        <p className="text-muted-foreground">
          Floresu parses nothing for you: you or your agent enter structured data. You can use both
          paths anytime.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <button
          type="button"
          onClick={onChooseManual}
          disabled={isBusy}
          className="border-input hover:bg-accent hover:text-accent-foreground focus-visible:border-ring focus-visible:ring-ring/50 flex flex-col gap-2 rounded-lg border p-5 text-left outline-none focus-visible:ring-[3px] disabled:pointer-events-none disabled:opacity-50"
        >
          <span className="text-base font-medium">Start manually</span>
          <span className="text-muted-foreground text-sm">
            Add your first worklog entry or profile fact by hand.
          </span>
        </button>
        <button
          type="button"
          onClick={onChooseConnect}
          disabled={isBusy}
          className="border-input hover:bg-accent hover:text-accent-foreground focus-visible:border-ring focus-visible:ring-ring/50 flex flex-col gap-2 rounded-lg border p-5 text-left outline-none focus-visible:ring-[3px] disabled:pointer-events-none disabled:opacity-50"
        >
          <span className="text-base font-medium">Connect your agent</span>
          <span className="text-muted-foreground text-sm">
            Link your AI client over MCP and let it import your history.
          </span>
        </button>
      </div>
    </div>
  );
}
