import type { RouteObject } from "react-router";
import { describe, expect, it } from "vitest";

import { appRoutes } from "@/routes";

/**
 * The Library route is wired additively under the app shell (behind the session
 * and onboarding guards), alongside the Home index route, without disturbing the
 * existing guard structure asserted in `routes.test.tsx`.
 */
describe("library route wiring", () => {
  it("nests /library under the guarded app shell", () => {
    const sessionGuard = appRoutes.find((route) => route.path === undefined);
    const onboardingGuard = sessionGuard?.children?.find((child) => child.path === undefined);
    const shell = onboardingGuard?.children?.find((child) => child.path === "/");
    const libraryRoute = shell?.children?.find((child: RouteObject) => child.path === "library");
    expect(libraryRoute).toBeDefined();
  });
});
