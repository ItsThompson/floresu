import { renderHook } from "@testing-library/react";
import { act } from "react";
import { describe, expect, it, vi } from "vitest";

import { useOnboarding } from "./useOnboarding";

/**
 * `completeOnboarding`, `onComplete`, and `onCompleteManual` are the hook's real
 * external boundaries (the auth session and the two router destinations), so they
 * are the appropriate things to substitute. Everything else runs for real.
 */
function renderOnboarding(overrides?: {
  completeOnboarding?: () => Promise<{ ok: true } | { ok: false; message: string }>;
  onComplete?: () => void;
  onCompleteManual?: () => void;
}) {
  const completeOnboarding = overrides?.completeOnboarding ?? vi.fn().mockResolvedValue({ ok: true });
  const onComplete = overrides?.onComplete ?? vi.fn();
  const onCompleteManual = overrides?.onCompleteManual ?? vi.fn();
  const view = renderHook(() => useOnboarding({ completeOnboarding, onComplete, onCompleteManual }));
  return { ...view, completeOnboarding, onComplete, onCompleteManual };
}

describe("useOnboarding", () => {
  it("starts on the first step with the count derived from STEPS", () => {
    const { result } = renderOnboarding();
    expect(result.current.state.stepIndex).toBe(0);
    expect(result.current.state.step).toBe("welcome");
    expect(result.current.state.stepCount).toBe(4);
    expect(result.current.state.isFirstStep).toBe(true);
    expect(result.current.state.isLastStep).toBe(false);
    expect(result.current.state.phase).toBe("idle");
  });

  it("advances and retreats through the steps, clamped at both ends", () => {
    const { result } = renderOnboarding();

    act(() => result.current.actions.goBack());
    expect(result.current.state.stepIndex).toBe(0); // clamped at the first step

    act(() => result.current.actions.goNext());
    expect(result.current.state.step).toBe("choose_path");

    act(() => result.current.actions.goNext());
    act(() => result.current.actions.goNext());
    expect(result.current.state.step).toBe("how_it_works");
    expect(result.current.state.isLastStep).toBe(true);

    act(() => result.current.actions.goNext());
    expect(result.current.state.stepIndex).toBe(3); // clamped at the last step

    act(() => result.current.actions.goBack());
    expect(result.current.state.step).toBe("connect_agent");
  });

  it("persists completion and calls onComplete on success", async () => {
    const completeOnboarding = vi.fn().mockResolvedValue({ ok: true });
    const onComplete = vi.fn();
    const { result } = renderOnboarding({ completeOnboarding, onComplete });

    await act(async () => {
      result.current.actions.complete();
    });

    expect(completeOnboarding).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(result.current.state.error).toBeNull();
  });

  it("surfaces an inline error and does not complete when persistence fails", async () => {
    const completeOnboarding = vi.fn().mockResolvedValue({ ok: false, message: "Could not save. Try again." });
    const onComplete = vi.fn();
    const { result } = renderOnboarding({ completeOnboarding, onComplete });

    await act(async () => {
      result.current.actions.complete();
    });

    expect(onComplete).not.toHaveBeenCalled();
    expect(result.current.state.phase).toBe("error");
    expect(result.current.state.error).toBe("Could not save. Try again.");
  });

  it("routes the manual path to onCompleteManual on success, not onComplete", async () => {
    const completeOnboarding = vi.fn().mockResolvedValue({ ok: true });
    const onComplete = vi.fn();
    const onCompleteManual = vi.fn();
    const { result } = renderOnboarding({ completeOnboarding, onComplete, onCompleteManual });

    await act(async () => {
      result.current.actions.completeManual();
    });

    expect(completeOnboarding).toHaveBeenCalledTimes(1);
    expect(onCompleteManual).toHaveBeenCalledTimes(1);
    expect(onComplete).not.toHaveBeenCalled();
    expect(result.current.state.error).toBeNull();
  });

  it("keeps the manual path in the wizard with an inline error when persistence fails", async () => {
    const completeOnboarding = vi.fn().mockResolvedValue({ ok: false, message: "Could not save. Try again." });
    const onCompleteManual = vi.fn();
    const { result } = renderOnboarding({ completeOnboarding, onCompleteManual });

    await act(async () => {
      result.current.actions.completeManual();
    });

    expect(onCompleteManual).not.toHaveBeenCalled();
    expect(result.current.state.phase).toBe("error");
    expect(result.current.state.error).toBe("Could not save. Try again.");
  });
});
