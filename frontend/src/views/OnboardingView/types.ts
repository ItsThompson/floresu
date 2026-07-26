import type { ReactNode } from "react";

import type { AuthResult } from "@/auth";

import type { STEPS } from "./constants";

/** One of the ordered onboarding steps. Derived from `STEPS` so the two cannot drift. */
export type OnboardingStep = (typeof STEPS)[number];

/** Completion lifecycle. `submitting` covers the in-flight persistence call. */
export type OnboardingPhase = "idle" | "submitting" | "error";

export interface OnboardingState {
  stepIndex: number;
  /** Total step count, derived from `STEPS`. */
  stepCount: number;
  /** The active step id, `STEPS[stepIndex]`. */
  step: OnboardingStep;
  isFirstStep: boolean;
  isLastStep: boolean;
  phase: OnboardingPhase;
  error: string | null;
}

export interface OnboardingActions {
  /** Advance to the next step (never past the last). */
  goNext: () => void;
  /** Return to the previous step (never before the first). */
  goBack: () => void;
  /** Finish onboarding via skip or the final step, then navigate Home. */
  complete: () => void;
  /** Finish onboarding via the manual path, then open the first entry form. */
  completeManual: () => void;
}

export interface UseOnboardingParams {
  /** Persists onboarding completion; resolves to an `AuthResult` (never throws). */
  completeOnboarding: () => Promise<AuthResult>;
  /** Called after a successful completion via skip or the final step (navigates Home). */
  onComplete: () => void;
  /** Called after a successful completion via the manual path (opens the entry form). */
  onCompleteManual: () => void;
}

/** Configuration sourced once at the view root and threaded to the steps as props. */
export interface OnboardingConfig {
  mcpUrl: string;
}

export interface OnboardingProgressProps {
  stepIndex: number;
  stepCount: number;
}

export interface OnboardingStepFrameProps {
  stepIndex: number;
  stepCount: number;
  canGoBack: boolean;
  onBack: () => void;
  onSkip: () => void;
  isBusy: boolean;
  error: string | null;
  children: ReactNode;
}

export interface WelcomeStepProps {
  onContinue: () => void;
}

export interface ChoosePathStepProps {
  onChooseManual: () => void;
  onChooseConnect: () => void;
  isBusy: boolean;
}

export interface ConnectAgentStepProps {
  mcpUrl: string;
  onContinue: () => void;
}

export interface HowItWorksStepProps {
  onFinish: () => void;
  isBusy: boolean;
}
