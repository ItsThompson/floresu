import { describe, expect, it } from "vitest";

import { AppShell } from "@/components/AppShell";
import { RequireAuth } from "@/components/RequireAuth";
import { RequireOnboarded } from "@/components/RequireOnboarded";
import { routeComponents } from "@/test/routeComponents";

import { LibraryView } from "./LibraryView";

/**
 * The Library route is wired additively under the app shell (behind the session
 * and onboarding guards), alongside the Home route, without disturbing the
 * existing guard structure asserted in `frontend/src/routes.test.tsx`.
 */
describe("library route wiring", () => {
  it("nests /library under the guarded app shell", () => {
    expect(routeComponents("/library")).toEqual([
      RequireAuth,
      RequireOnboarded,
      AppShell,
      LibraryView,
    ]);
  });
});
