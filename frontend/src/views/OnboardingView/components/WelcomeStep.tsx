import { Button } from "@/components/ui/button";

import type { WelcomeStepProps } from "../types";

/**
 * Opening step: what Floresu is and, crucially, what it is not. It runs no AI of
 * its own and parses nothing; the user or their agent enters structured data.
 *
 * Takes the step's one serif display moment: this is the app's first greeting.
 */
export function WelcomeStep({ onContinue }: WelcomeStepProps) {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="display-m">Welcome to Floresu</h1>
      <p className="text-muted-foreground">
        Your living career record. Floresu stores your professional history and hands it to your own
        AI agent over MCP. It runs no AI of its own and parses nothing for you.
      </p>
      <Button onClick={onContinue}>Get started</Button>
    </div>
  );
}
