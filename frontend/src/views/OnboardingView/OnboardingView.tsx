import type { ReactNode } from "react";
import { Navigate, useNavigate } from "react-router";

import { useAuth } from "@/auth";

import { ChoosePathStep } from "./components/ChoosePathStep";
import { ConnectAgentStep } from "./components/ConnectAgentStep";
import { HowItWorksStep } from "./components/HowItWorksStep";
import { OnboardingStepFrame } from "./components/OnboardingStepFrame";
import { WelcomeStep } from "./components/WelcomeStep";
import { DEFAULT_MCP_URL } from "./constants";
import { useOnboarding } from "./hooks/useOnboarding";
import type { OnboardingStep } from "./types";

/**
 * The getting-started wizard (chrome-free, full viewport). Composes the state
 * machine, the shared step frame, and the ordered steps. An already-onboarded
 * user never sees it: the view redirects Home, mirroring how `AuthView`
 * redirects an authenticated user. The MCP URL is sourced once here and threaded
 * to the connect step; the steps read no environment themselves.
 */
export function OnboardingView() {
  const { user, completeOnboarding } = useAuth();
  const navigate = useNavigate();
  const { state, actions } = useOnboarding({
    completeOnboarding,
    onComplete: () => navigate("/", { replace: true }),
  });

  if (user?.has_completed_onboarding) {
    return <Navigate to="/" replace />;
  }

  const mcpUrl = import.meta.env.VITE_MCP_URL ?? DEFAULT_MCP_URL;
  const isBusy = state.phase === "submitting";

  const steps: Record<OnboardingStep, ReactNode> = {
    welcome: <WelcomeStep onContinue={actions.goNext} />,
    choose_path: (
      <ChoosePathStep
        onChooseManual={actions.complete}
        onChooseConnect={actions.goNext}
        isBusy={isBusy}
      />
    ),
    connect_agent: <ConnectAgentStep mcpUrl={mcpUrl} onContinue={actions.goNext} />,
    how_it_works: <HowItWorksStep onFinish={actions.complete} isBusy={isBusy} />,
  };

  return (
    <OnboardingStepFrame
      stepIndex={state.stepIndex}
      stepCount={state.stepCount}
      canGoBack={!state.isFirstStep}
      onBack={actions.goBack}
      onSkip={actions.complete}
      isBusy={isBusy}
      error={state.error}
    >
      {steps[state.step]}
    </OnboardingStepFrame>
  );
}
