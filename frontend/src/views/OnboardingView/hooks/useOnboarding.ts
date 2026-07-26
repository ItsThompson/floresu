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
 * counter of their own. `completeOnboarding`, `onComplete`, and
 * `onCompleteManual` are injected (the boundary to the auth session and the two
 * router destinations), which keeps this hook a pure, independently testable
 * unit.
 */
export function useOnboarding({ completeOnboarding, onComplete, onCompleteManual }: UseOnboardingParams): UseOnboarding {
  const [stepIndex, setStepIndex] = useState(0);
  const [phase, setPhase] = useState<OnboardingPhase>("idle");
  const [error, setError] = useState<string | null>(null);

  const goNext = useCallback(() => {
    setStepIndex((current) => Math.min(current + 1, STEPS.length - 1));
  }, []);

  const goBack = useCallback(() => {
    setStepIndex((current) => Math.max(current - 1, 0));
  }, []);

  // The shared completion side effect: persist onboarding, then run the given
  // success navigation. A failed completion keeps the user in the wizard with an
  // inline error, whichever path triggered it.
  const runCompletion = useCallback(
    (onSuccess: () => void) => {
      setPhase("submitting");
      setError(null);
      void completeOnboarding().then((result) => {
        if (result.ok) {
          onSuccess();
          return;
        }
        setPhase("error");
        setError(result.message);
      });
    },
    [completeOnboarding],
  );

  const complete = useCallback(() => runCompletion(onComplete), [runCompletion, onComplete]);
  const completeManual = useCallback(
    () => runCompletion(onCompleteManual),
    [runCompletion, onCompleteManual],
  );

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
    () => ({ goNext, goBack, complete, completeManual }),
    [goNext, goBack, complete, completeManual],
  );

  return { state, actions };
}
