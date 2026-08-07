import { Button } from "@/components/ui/button";

import type { HowItWorksStepProps } from "../types";

/**
 * Closing step: the three anchor flows in one glance. Finishing it completes
 * onboarding and lands the user on Home.
 *
 * Takes the step's one serif display moment; the flows below it stay in the
 * grotesque so the heading is the only display line on screen.
 */
export function HowItWorksStep({ onFinish, isBusy }: HowItWorksStepProps) {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="display-m">How Floresu works</h1>
      <ul className="text-muted-foreground flex list-disc flex-col gap-2 pl-5">
        <li>Capture your work in a worklog as it happens.</li>
        <li>Your agent refines it into reusable library bullets over time.</li>
        <li>For a job, your agent assembles a tailored resume you refine, finalize, and export.</li>
      </ul>
      <Button onClick={onFinish} disabled={isBusy}>
        Finish
      </Button>
    </div>
  );
}
