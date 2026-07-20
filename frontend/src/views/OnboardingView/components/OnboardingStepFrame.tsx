import { Button } from "@/components/ui/button";

import type { OnboardingStepFrameProps } from "../types";
import { OnboardingProgress } from "./OnboardingProgress";

/**
 * Chrome-free full-viewport shell shared by every onboarding step: the progress
 * indicator, the active step's body, an inline completion error, and the
 * navigation controls. Back is offered on every step except the first; Skip is
 * available from every step. Both controls are disabled while a completion call
 * is in flight.
 */
export function OnboardingStepFrame({
  stepIndex,
  stepCount,
  canGoBack,
  onBack,
  onSkip,
  isBusy,
  error,
  children,
}: OnboardingStepFrameProps) {
  return (
    <main className="bg-background text-foreground flex min-h-svh flex-col items-center justify-center p-6">
      <section className="flex w-full max-w-[40rem] flex-col gap-8">
        <OnboardingProgress stepIndex={stepIndex} stepCount={stepCount} />
        {children}
        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}
        <div className="flex items-center justify-between">
          {canGoBack ? (
            <Button variant="outline" onClick={onBack} disabled={isBusy}>
              Back
            </Button>
          ) : (
            <span />
          )}
          <Button variant="ghost" onClick={onSkip} disabled={isBusy}>
            Skip
          </Button>
        </div>
      </section>
    </main>
  );
}
