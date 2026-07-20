import { describe, expect, it } from "vitest";
import type { RouteObject } from "react-router";

import { appRoutes } from "./routes";

/**
 * Structural routing invariants asserted without rendering: the chrome-free auth
 * screens are top-level (reachable without a session); the onboarding wizard is
 * guarded by the session but sits outside the app shell; and the in-app routes
 * are nested behind BOTH the session guard and the onboarding guard, so neither
 * "/" nor "/onboarding" can render unguarded.
 */
describe("appRoutes", () => {
  const guard = appRoutes.find((route) => route.path === undefined);
  const guardChildren: RouteObject[] = guard?.children ?? [];

  it("exposes /signin and /signup outside the auth guard", () => {
    const topLevelPaths = appRoutes.map((route) => route.path);
    expect(topLevelPaths).toContain("/signin");
    expect(topLevelPaths).toContain("/signup");
  });

  it("nests everything else under a single guard layout route", () => {
    // The session guard is the one route with no `path`; neither the wizard nor
    // the app shell is a top-level entry, so neither can render unguarded.
    expect(guard).toBeDefined();
    expect(appRoutes.some((route) => route.path === "/")).toBe(false);
    expect(appRoutes.some((route) => route.path === "/onboarding")).toBe(false);
  });

  it("places the onboarding wizard inside the session guard but outside the app shell", () => {
    const onboarding = guardChildren.find((child) => child.path === "/onboarding");
    expect(onboarding).toBeDefined();
    // The wizard renders its own element directly (chrome-free), not through the shell.
    expect(onboarding?.children).toBeUndefined();
  });

  it("places the consent screen inside the session guard but outside the onboarding guard", () => {
    // Session-gated (a direct child of the guard) yet chrome-free and not behind
    // the onboarding guard, so a connect-time consent is never bounced to the wizard.
    const consent = guardChildren.find((child) => child.path === "/authorize");
    expect(consent).toBeDefined();
    expect(consent?.children).toBeUndefined();
  });

  it("gates the app shell and its index route behind the onboarding guard", () => {
    // The shell lives under a second pathless layout route (the onboarding guard),
    // not as a direct child of the session guard.
    const onboardingGuard = guardChildren.find((child) => child.path === undefined);
    expect(onboardingGuard).toBeDefined();
    const shell = onboardingGuard?.children?.find((child) => child.path === "/");
    expect(shell?.children?.some((child) => child.index)).toBe(true);
  });
});
