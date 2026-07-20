import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OnboardingStepFrame } from "./OnboardingStepFrame";

function renderFrame(overrides?: Partial<Parameters<typeof OnboardingStepFrame>[0]>) {
  const props = {
    stepIndex: 1,
    stepCount: 4,
    canGoBack: true,
    onBack: vi.fn(),
    onSkip: vi.fn(),
    isBusy: false,
    error: null as string | null,
    children: <p>step body</p>,
    ...overrides,
  };
  render(<OnboardingStepFrame {...props} />);
  return props;
}

describe("OnboardingStepFrame", () => {
  it("renders the completion error inline as an alert", () => {
    renderFrame({ error: "Could not finish onboarding. Please try again." });
    expect(screen.getByRole("alert")).toHaveTextContent("Could not finish onboarding. Please try again.");
  });

  it("shows no alert when there is no error", () => {
    renderFrame({ error: null });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("hides Back on the first step and disables the controls while busy", () => {
    renderFrame({ canGoBack: false, isBusy: true });
    expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Skip" })).toBeDisabled();
  });
});
