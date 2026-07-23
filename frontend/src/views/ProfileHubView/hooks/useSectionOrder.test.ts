import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { DEFAULT_SECTION_ORDER, SECTION_ORDER_STORAGE_KEY } from "../constants";
import { useSectionOrder } from "./useSectionOrder";

/**
 * Unit tests for the localStorage reconciliation in `useSectionOrder`. They drive
 * the hook's public interface with `renderHook` and seed `localStorage` before
 * render, since the corrupt/stale/non-array inputs are reachable only through a
 * pre-existing stored value (`reorder` accepts a typed `SectionId[]`). No MSW: the
 * hook makes no network calls. The private `reconcile` is never referenced.
 */

/** Seed the stored order with an already-serialized string, exactly as the browser would hold it. */
function seedRaw(raw: string): void {
  window.localStorage.setItem(SECTION_ORDER_STORAGE_KEY, raw);
}

/** Seed the stored order with a value that is JSON-serialized first (the normal write shape). */
function seedValue(value: unknown): void {
  seedRaw(JSON.stringify(value));
}

describe("useSectionOrder", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => window.localStorage.clear());

  describe("falls back to the default order", () => {
    it("when the key is absent", () => {
      const { result } = renderHook(() => useSectionOrder());
      expect(result.current.order).toEqual(DEFAULT_SECTION_ORDER);
    });

    it("when the stored value is a corrupt, non-JSON string", () => {
      seedRaw("{not json");
      const { result } = renderHook(() => useSectionOrder());
      expect(result.current.order).toEqual(DEFAULT_SECTION_ORDER);
    });

    it("when the stored value is valid JSON but a number, not an array", () => {
      seedRaw("42");
      const { result } = renderHook(() => useSectionOrder());
      expect(result.current.order).toEqual(DEFAULT_SECTION_ORDER);
    });

    it("when the stored value is valid JSON but an object, not an array", () => {
      seedRaw("{}");
      const { result } = renderHook(() => useSectionOrder());
      expect(result.current.order).toEqual(DEFAULT_SECTION_ORDER);
    });
  });

  describe("reconciles a stored array against the current section set", () => {
    it("drops unknown ids and keeps valid ones in their stored order", () => {
      seedValue(["projects", "totally-unknown", "work"]);
      const { result } = renderHook(() => useSectionOrder());
      expect(result.current.order).toEqual(["projects", "work", "skills", "education", "identity"]);
    });

    it("appends missing sections after the kept ids in default order", () => {
      seedValue(["identity", "skills"]);
      const { result } = renderHook(() => useSectionOrder());
      expect(result.current.order).toEqual(["identity", "skills", "work", "projects", "education"]);
    });

    it("preserves a fully valid, reordered array verbatim", () => {
      const reordered = ["identity", "education", "skills", "projects", "work"];
      seedValue(reordered);
      const { result } = renderHook(() => useSectionOrder());
      expect(result.current.order).toEqual(reordered);
    });

    it("keeps duplicate ids verbatim (no dedup is applied)", () => {
      seedValue(["work", "work"]);
      const { result } = renderHook(() => useSectionOrder());
      expect(result.current.order).toEqual([
        "work",
        "work",
        "projects",
        "skills",
        "education",
        "identity",
      ]);
    });
  });

  describe("reorder", () => {
    it("writes the reconciled value, not the raw partial array, and reflects it in order", () => {
      const { result } = renderHook(() => useSectionOrder());

      act(() => result.current.reorder(["projects", "work"]));

      const reconciled = ["projects", "work", "skills", "education", "identity"];
      expect(result.current.order).toEqual(reconciled);

      const stored = JSON.parse(window.localStorage.getItem(SECTION_ORDER_STORAGE_KEY) ?? "null");
      expect(stored).toEqual(reconciled);
    });
  });
});
