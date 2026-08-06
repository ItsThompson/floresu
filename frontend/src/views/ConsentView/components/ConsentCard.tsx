import { Check, X } from "lucide-react";

import { Button } from "@/components/ui/button";

import type { ConsentCardProps } from "../types";

/**
 * The single plain-language statement of what the one full read-write scope
 * grants. There is exactly one access level, so this is fixed copy, not a
 * per-scope list: consent presents no partial-scope choices.
 */
const ACCESS_STATEMENT = "It will read and write your worklog, profile, library, and resumes.";

/**
 * The consent card: the trust moment when a signed-in human connects an agent.
 * Quiet and legible, it names the agent, states plainly what it may read and
 * write, shows who is signed in, and offers Deny and Approve. The accent
 * (primary) treatment lands on Approve, the primary action; Deny is a ghost, and
 * the two are distinguished by label AND icon AND button weight, never by color
 * alone.
 *
 * The serif wordmark opens the card because this screen is reached from an
 * agent's redirect rather than from the app chrome: seeing who is asking is part
 * of the decision. It is the brand signature, not one of the view-level display
 * moments, so it carries no display utility.
 */
export function ConsentCard({
  agentName,
  userEmail,
  isDeciding,
  onApprove,
  onDeny,
}: ConsentCardProps) {
  return (
    <main className="bg-background text-foreground flex min-h-svh items-center justify-center p-6">
      <section className="bg-card text-card-foreground border-border flex w-full max-w-[26rem] flex-col gap-5 rounded-xl border p-8 text-center">
        <span className="font-serif text-xl font-medium lowercase tracking-tight">floresu</span>
        <h1 className="text-xl font-semibold tracking-tight">Connect “{agentName}” to Floresu?</h1>
        <p className="bg-muted text-foreground rounded-md px-4 py-3">{ACCESS_STATEMENT}</p>
        <p className="text-muted-foreground text-sm">
          Signed in as <span className="text-foreground font-medium">{userEmail}</span>
        </p>
        <div className="flex items-center gap-3">
          <Button variant="ghost" className="flex-1" onClick={onDeny} disabled={isDeciding}>
            <X aria-hidden />
            Deny
          </Button>
          <Button variant="default" className="flex-1" onClick={onApprove} disabled={isDeciding}>
            <Check aria-hidden />
            Approve
          </Button>
        </div>
      </section>
    </main>
  );
}
