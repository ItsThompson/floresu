import { Check, ShieldCheck, X } from "lucide-react";

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
 * (primary) treatment lands on Approve, the primary action; Deny and Approve are
 * distinguished by label AND icon AND button shape, never by color alone.
 */
export function ConsentCard({ agentName, userEmail, isDeciding, onApprove, onDeny }: ConsentCardProps) {
  return (
    <main className="bg-background text-foreground flex min-h-svh items-center justify-center p-6">
      <section className="border-border flex w-full max-w-[26rem] flex-col gap-6 rounded-xl border p-8">
        <ShieldCheck aria-hidden className="text-primary size-8" />
        <div className="flex flex-col gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">
            Connect “{agentName}” to Floresu?
          </h1>
          <p className="text-muted-foreground">{ACCESS_STATEMENT}</p>
          <p className="text-muted-foreground text-sm">
            Signed in as <span className="text-foreground font-medium">{userEmail}</span>
          </p>
        </div>
        <div className="flex items-center justify-end gap-3">
          <Button variant="outline" onClick={onDeny} disabled={isDeciding}>
            <X aria-hidden />
            Deny
          </Button>
          <Button variant="default" onClick={onApprove} disabled={isDeciding}>
            <Check aria-hidden />
            Approve
          </Button>
        </div>
      </section>
    </main>
  );
}
