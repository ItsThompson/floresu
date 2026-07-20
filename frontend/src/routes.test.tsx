import { describe, expect, it } from "vitest";

import { appRoutes } from "./routes";

/**
 * Structural routing invariants asserted without rendering: the chrome-free auth
 * screens are top-level (reachable without a session), and the in-app routes are
 * nested under the RequireAuth guard rather than exposed directly.
 */
describe("appRoutes", () => {
  it("exposes /signin and /signup outside the auth guard", () => {
    const topLevelPaths = appRoutes.map((route) => route.path);
    expect(topLevelPaths).toContain("/signin");
    expect(topLevelPaths).toContain("/signup");
  });

  it("nests the app shell and its routes under a single guard layout route", () => {
    // The guard is the one route with no `path` (a layout route) wrapping the
    // shell; "/" is not a top-level entry, so it cannot render unguarded.
    const guard = appRoutes.find((route) => route.path === undefined);
    expect(guard).toBeDefined();
    const shell = guard?.children?.find((child) => child.path === "/");
    expect(shell?.children?.some((child) => child.index)).toBe(true);
    expect(appRoutes.some((route) => route.path === "/")).toBe(false);
  });
});
