import { describe, expect, it } from "vitest";
import type { RouteObject } from "react-router";

import { AppShell } from "@/components/AppShell";
import { RequireAuth } from "@/components/RequireAuth";
import { RequireOnboarded } from "@/components/RequireOnboarded";
import { routeComponents } from "@/test/routeComponents";
import { HomeView } from "@/views/HomeView";
import { LandingView } from "@/views/LandingView";
import { WorklogView } from "@/views/WorklogView";

import { appRoutes } from "./routes";

/**
 * Structural routing invariants asserted without rendering: the public page and
 * the chrome-free auth screens are top-level (reachable without a session); the
 * onboarding wizard is guarded by the session but sits outside the app shell;
 * and the in-app routes are nested behind BOTH the session guard and the
 * onboarding guard, so neither "/home" nor "/onboarding" can render unguarded.
 */
describe("appRoutes", () => {
  const guard = appRoutes.find((route) => route.path === undefined);
  const guardChildren: RouteObject[] = guard?.children ?? [];

  it("exposes /signin and /signup outside the auth guard", () => {
    const topLevelPaths = appRoutes.map((route) => route.path);
    expect(topLevelPaths).toContain("/signin");
    expect(topLevelPaths).toContain("/signup");
  });

  it("serves the public page at / outside every guard", () => {
    expect(appRoutes.map((route) => route.path)).toContain("/");
    // The reason for the top-level placement: "/" resolves to the public page
    // alone, so an anonymous visitor is never bounced to /signin and no app
    // chrome wraps the page.
    expect(routeComponents("/")).toEqual([LandingView]);
  });

  it("nests every in-app route under a single guard layout route", () => {
    // The session guard is the one route with no `path`; neither the wizard nor
    // Home is a top-level entry, so neither can render unguarded.
    expect(guard).toBeDefined();
    expect(appRoutes.filter((route) => route.path === undefined)).toHaveLength(1);
    expect(appRoutes.some((route) => route.path === "/onboarding")).toBe(false);
    expect(appRoutes.some((route) => route.path === "/home")).toBe(false);
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

  it("mounts the app shell as a pathless layout route with no index route", () => {
    // The shell lives under a second pathless layout route (the onboarding guard),
    // not as a direct child of the session guard. It claims no path and no index
    // route, so nothing behind the guards can match "/" and shadow the public page.
    const onboardingGuard = guardChildren.find((child) => child.path === undefined);
    expect(onboardingGuard).toBeDefined();
    const shell = onboardingGuard?.children?.find((child) => child.path === undefined);
    expect(shell).toBeDefined();
    expect(shell?.children?.some((child) => child.index)).toBe(false);
  });

  it("gates Home at /home behind the session guard, the onboarding guard, and the shell", () => {
    expect(routeComponents("/home")).toEqual([RequireAuth, RequireOnboarded, AppShell, HomeView]);
  });

  it("leaves the other in-app paths where they were", () => {
    // The shell claims no path segment, so its children still resolve at the app
    // root: giving Home an explicit path moved no other URL.
    expect(routeComponents("/worklog")).toEqual([
      RequireAuth,
      RequireOnboarded,
      AppShell,
      WorklogView,
    ]);
  });
});
