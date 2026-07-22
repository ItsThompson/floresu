import { describe, expect, it } from "vitest";

import { extractProblem, PROBLEM_FALLBACK_MESSAGE } from "./problemDetail";

describe("extractProblem", () => {
  it("prefers detail over title for the message", () => {
    const problem = extractProblem({ detail: "That label is taken.", title: "Conflict" });
    expect(problem.message).toBe("That label is taken.");
  });

  it("falls back to title when detail is absent", () => {
    expect(extractProblem({ title: "Conflict" }).message).toBe("Conflict");
  });

  it("uses the fallback message for an empty or non-object body", () => {
    expect(extractProblem(undefined).message).toBe(PROBLEM_FALLBACK_MESSAGE);
    expect(extractProblem(new Error("network")).message).toBe(PROBLEM_FALLBACK_MESSAGE);
  });

  it("reads a string field-error map and ignores non-string entries", () => {
    expect(extractProblem({ fields: { display_label: "Required" } }).fields).toEqual({
      display_label: "Required",
    });
    expect(extractProblem({ fields: { n: 1 } }).fields).toBeUndefined();
  });

  it("parses the structural violations array with stringified ids", () => {
    const problem = extractProblem({
      detail: "Pick a replacement.",
      violations: [
        { rule: "identity_variant_replacement_required", ids: [7, 9], message: "in use" },
      ],
    });
    expect(problem.violations).toEqual([
      { rule: "identity_variant_replacement_required", ids: ["7", "9"], message: "in use" },
    ]);
  });

  it("returns an empty violations array when none are present", () => {
    expect(extractProblem({ detail: "nope" }).violations).toEqual([]);
  });
});
