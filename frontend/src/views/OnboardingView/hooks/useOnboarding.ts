import { useCallback, useMemo, useState } from "react";

import { STEPS } from "../constants";
import type { OnboardingActions, OnboardingPhase, OnboardingState, UseOnboardingParams } from "../types";

interface UseOnboarding {
  state: OnboardingState;
  actions: OnboardingActions;
}

/**
 * The onboarding state machine: the current step index plus the completion
 * lifecycle. Order and count come entirely from `STEPS`, so the steps hold no
 * counter of their own. `completeOnboarding` and `onComplete` are injected (the
 * boundary to the auth session and the router), which keeps this hook a pure,
 * independently testable unit.
 */
export function useOnboarding({ completeOnboarding, onComplete }: UseOnboardingParams): UseOnboarding {
  const [stepIndex, setStepIndex] = useState(0);
  const [phase, setPhase] = useState<OnboardingPhase>("idle");
  const [error, setError] = useState<string | null>(null);

  const goNext = useCallback(() => {
    setStepIndex((current) => Math.min(current + 1, STEPS.length - 1));
  }, []);

  const goBack = useCallback(() => {
    setStepIndex((current) => Math.max(current - 1, 0));
  }, []);

  const complete = useCallback(() => {
    setPhase("submitting");
    setError(null);
    void completeOnboarding().then((result) => {
      if (result.ok) {
        onComplete();
        return;
      }
      // A failed completion keeps the user in the wizard with an inline error.
      setPhase("error");
      setError(result.message);
    });
  }, [completeOnboarding, onComplete]);

  const state = useMemo<OnboardingState>(
    () => ({
      stepIndex,
      stepCount: STEPS.length,
      step: STEPS[stepIndex],
      isFirstStep: stepIndex === 0,
      isLastStep: stepIndex === STEPS.length - 1,
      phase,
      error,
    }),
    [stepIndex, phase, error],
  );

  const actions = useMemo<OnboardingActions>(
    () => ({ goNext, goBack, complete }),
    [goNext, goBack, complete],
  );

  return { state, actions };
}
