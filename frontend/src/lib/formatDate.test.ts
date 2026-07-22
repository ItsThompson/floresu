import { describe, expect, it } from "vitest";

import {
  formatDateRange,
  formatDay,
  formatDayYear,
  formatMonthYear,
  monthKey,
  monthKeyLabel,
} from "./formatDate";

describe("formatMonthYear", () => {
  it("formats an ISO day as MMM YYYY in UTC", () => {
    expect(formatMonthYear("2025-09-04")).toBe("Sep 2025");
  });

  it("returns null for null or an unparseable value", () => {
    expect(formatMonthYear(null)).toBeNull();
    expect(formatMonthYear("not-a-date")).toBeNull();
  });
});

describe("formatDateRange", () => {
  it("renders an open-ended range as Present", () => {
    expect(formatDateRange("2025-09-01", null)).toBe("Sep 2025 – Present");
  });

  it("renders a closed range", () => {
    expect(formatDateRange("2023-01-01", "2024-06-01")).toBe("Jan 2023 – Jun 2024");
  });

  it("renders just the end when there is no start", () => {
    expect(formatDateRange(null, "2024-06-01")).toBe("Jun 2024");
  });

  it("is empty when both dates are missing", () => {
    expect(formatDateRange(null, null)).toBe("");
  });
});

describe("month bucketing", () => {
  it("keys by UTC year-month and labels it", () => {
    expect(monthKey("2025-09-30")).toBe("2025-09");
    expect(monthKeyLabel("2025-09")).toBe("September 2025");
  });

  it("formats a day label", () => {
    expect(formatDay("2025-07-18")).toBe("Jul 18");
  });

  it("formats a day label carrying the year", () => {
    expect(formatDayYear("2026-07-18T09:30:00Z")).toBe("Jul 18, 2026");
    expect(formatDayYear("not-a-date")).toBe("not-a-date");
  });
});
