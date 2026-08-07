import { describe, expect, it } from "vitest";

import { resolveStartDestination } from "./resolveStartDestination";

describe("resolveStartDestination", () => {
  it("sends an anonymous visitor to signup", () => {
    expect(resolveStartDestination({ status: "anonymous" })).toBe("/signup");
  });

  it("sends a signed-in visitor who has not finished onboarding back to the wizard", () => {
    expect(
      resolveStartDestination({ status: "authenticated", hasCompletedOnboarding: false }),
    ).toBe("/onboarding");
  });

  it("sends a signed-in, onboarded visitor into the app", () => {
    expect(resolveStartDestination({ status: "authenticated", hasCompletedOnboarding: true })).toBe(
      "/home",
    );
  });
});
