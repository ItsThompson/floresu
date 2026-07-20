import { TriangleAlert } from "lucide-react";

import type { ConsentErrorProps } from "../types";

/**
 * The consent error state: shown when the parked request is missing, invalid, or
 * expired, or when a decision fails. It never renders an approve action, so a
 * broken request can never be silently approved: the human is told to restart
 * the connection from their agent.
 */
export function ConsentError({ message }: ConsentErrorProps) {
  return (
    <main className="bg-background text-foreground flex min-h-svh items-center justify-center p-6">
      <section
        role="alert"
        className="border-border flex w-full max-w-[26rem] flex-col gap-4 rounded-xl border p-8"
      >
        <TriangleAlert aria-hidden className="text-muted-foreground size-8" />
        <h1 className="text-xl font-semibold tracking-tight">Connection request unavailable</h1>
        <p className="text-muted-foreground text-sm">{message}</p>
      </section>
    </main>
  );
}
