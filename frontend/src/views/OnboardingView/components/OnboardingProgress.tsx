import type { OnboardingProgressProps } from "../types";

/**
 * Step indicator for the wizard. Shows the current position as text ("Step X of
 * N") so the count is never conveyed by the segment fill alone, with a filled
 * segment per completed-or-current step. Both values derive from `STEPS` via the
 * hook, so this component holds no notion of order itself.
 */
export function OnboardingProgress({ stepIndex, stepCount }: OnboardingProgressProps) {
  return (
    <div className="flex flex-col gap-2" role="group" aria-label="Onboarding progress">
      <p className="text-muted-foreground text-sm">
        Step {stepIndex + 1} of {stepCount}
      </p>
      <ol className="flex gap-1.5" aria-hidden="true">
        {Array.from({ length: stepCount }, (_, index) => (
          <li
            key={index}
            className={`h-1.5 flex-1 rounded-full ${index <= stepIndex ? "bg-primary" : "bg-muted"}`}
          />
        ))}
      </ol>
    </div>
  );
}
