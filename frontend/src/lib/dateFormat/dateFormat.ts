// UTC formatters: entry dates are calendar dates (`yyyy-mm-dd`) with no zone, so
// formatting in UTC avoids a local-timezone off-by-one on the day and month.
const MONTH_LABEL = new Intl.DateTimeFormat("en-US", {
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});
const DAY_LABEL = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "2-digit",
  timeZone: "UTC",
});

/** Format an entry date as its full month, e.g. "July 2026". */
export function formatMonthLabel(isoDate: string): string {
  return MONTH_LABEL.format(new Date(isoDate));
}

/** Format an entry date as a short day, e.g. "Jul 18". */
export function formatDayLabel(isoDate: string): string {
  return DAY_LABEL.format(new Date(isoDate));
}
