import { useRef, type ReactNode } from "react";
import { Navigate, useNavigate } from "react-router";

import { useAuth } from "@/auth";
import { resolveMcpUrl } from "@/lib/mcpUrl";
import { worklogNewEntryPath } from "@/lib/worklogPaths";

import { ChoosePathStep } from "./components/ChoosePathStep";
import { ConnectAgentStep } from "./components/ConnectAgentStep";
import { HowItWorksStep } from "./components/HowItWorksStep";
import { OnboardingStepFrame } from "./components/OnboardingStepFrame";
import { WelcomeStep } from "./components/WelcomeStep";
import { useOnboarding } from "./hooks/useOnboarding";
import type { OnboardingStep } from "./types";

/**
 * The getting-started wizard (chrome-free, full viewport). Composes the state
 * machine, the shared step frame, and the ordered steps. A user who arrives
 * already onboarded never sees it: the view redirects Home, mirroring how
 * `AuthView` redirects an authenticated user. Onboarding status is captured at
 * mount so a completion performed here routes through the completion handler
 * (which chooses Home or the worklog entry form) rather than being preempted by
 * the redirect. The MCP URL is sourced once here and threaded to the connect
 * step; the steps read no environment themselves.
 */
export function OnboardingView() {
  const { user, completeOnboarding } = useAuth();
  const navigate = useNavigate();
  // Captured once: a user who was already onboarded on arrival is bounced Home; a
  // user who completes onboarding in this session is navigated by the handler.
  const arrivedOnboarded = useRef(user?.has_completed_onboarding ?? false);
  const { state, actions } = useOnboarding({
    completeOnboarding,
    onComplete: () => navigate("/", { replace: true }),
    onCompleteManual: () => navigate(worklogNewEntryPath(), { replace: true }),
  });

  if (arrivedOnboarded.current) {
    return <Navigate to="/" replace />;
  }

  const mcpUrl = resolveMcpUrl();
  const isBusy = state.phase === "submitting";

  const steps: Record<OnboardingStep, ReactNode> = {
    welcome: <WelcomeStep onContinue={actions.goNext} />,
    choose_path: (
      <ChoosePathStep
        onChooseManual={actions.completeManual}
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
