import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useAuth } from "./useAuth";

describe("useAuth", () => {
  it("throws when used outside an AuthProvider", () => {
    expect(() => renderHook(() => useAuth())).toThrow(/within an AuthProvider/);
  });
});
