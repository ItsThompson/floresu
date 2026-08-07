import { PenLine, Plug } from "lucide-react";

import { Button } from "@/components/ui/button";

import type { ChoosePathStepProps } from "../types";

const CHOICE_CARD =
  "bg-card text-card-foreground border-border flex flex-col gap-3 rounded-lg border p-6";

const CHOICE_ICON =
  "bg-accent text-accent-foreground flex size-9 items-center justify-center rounded-full";

/**
 * The cold-start choice: start manually or connect an agent. Either action
 * finishes onboarding or advances the wizard rather than visiting a URL, so both
 * are buttons. The copy states plainly that Floresu parses nothing, and that
 * both paths remain available later.
 *
 * This is the one screen where the wizard is loud: the manual path carries the
 * primary fill because it needs nothing set up and produces the first entry
 * immediately, while connecting an agent stays a full-strength secondary.
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
        <article className={CHOICE_CARD}>
          <div className="flex items-center gap-3">
            <span className={CHOICE_ICON}>
              <PenLine aria-hidden className="size-4" />
            </span>
            <h2 className="font-semibold">You write</h2>
          </div>
          <p className="text-muted-foreground flex-1 text-sm">
            Add your first worklog entry or profile fact by hand.
          </p>
          <Button onClick={onChooseManual} disabled={isBusy}>
            Start manually
          </Button>
        </article>
        <article className={CHOICE_CARD}>
          <div className="flex items-center gap-3">
            <span className={CHOICE_ICON}>
              <Plug aria-hidden className="size-4" />
            </span>
            <h2 className="font-semibold">Your agent writes</h2>
          </div>
          <p className="text-muted-foreground flex-1 text-sm">
            Link your AI client over MCP and let it import your history.
          </p>
          <Button variant="secondary" onClick={onChooseConnect} disabled={isBusy}>
            Connect your agent
          </Button>
        </article>
      </div>
    </div>
  );
}
