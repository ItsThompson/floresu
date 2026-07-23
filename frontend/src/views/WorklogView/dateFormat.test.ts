import { describe, expect, it } from "vitest";

import { formatDayLabel, formatMonthLabel } from "./dateFormat";

describe("formatMonthLabel / formatDayLabel", () => {
  it("formats a calendar date in UTC without a timezone off-by-one", () => {
    expect(formatMonthLabel("2026-07-01")).toBe("July 2026");
    expect(formatDayLabel("2026-07-18")).toBe("Jul 18");
    // The first of the month must not slip to the previous month/day.
    expect(formatDayLabel("2026-01-01")).toBe("Jan 01");
  });
});
