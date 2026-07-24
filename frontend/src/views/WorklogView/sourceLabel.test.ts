import { describe, expect, it } from "vitest";

import { buildSource } from "./test-support/fixtures";
import { sourceLabel } from "./sourceLabel";

describe("sourceLabel", () => {
  const sources = [buildSource({ id: 10, display_label: "Acme — Senior Engineer" })];

  it("returns the display label for a known source", () => {
    expect(sourceLabel(sources, 10)).toBe("Acme — Senior Engineer");
  });

  it("falls back to a stable placeholder for an unknown source", () => {
    expect(sourceLabel(sources, 99)).toBe("Source 99");
  });
});
