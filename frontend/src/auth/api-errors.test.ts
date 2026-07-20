import { describe, expect, it } from "vitest";

import { toAuthResult } from "./api-errors";

describe("toAuthResult", () => {
  it("uses the problem+json detail and field map", () => {
    const result = toAuthResult({
      detail: "An account with this email already exists.",
      fields: { email: "This email is already registered." },
    });
    expect(result).toEqual({
      ok: false,
      message: "An account with this email already exists.",
      fields: { email: "This email is already registered." },
    });
  });

  it("falls back to the title when detail is absent", () => {
    const result = toAuthResult({ title: "Validation failed" });
    expect(result).toEqual({ ok: false, message: "Validation failed", fields: undefined });
  });

  it("degrades to a generic message for an empty or malformed body", () => {
    const result = toAuthResult(undefined);
    expect(result).toEqual({
      ok: false,
      message: "Something went wrong. Please try again.",
      fields: undefined,
    });
  });
});
