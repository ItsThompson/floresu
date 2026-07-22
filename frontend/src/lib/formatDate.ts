/**
 * Shared date formatting for profile and worklog surfaces. Backend dates are ISO
 * day strings (or null); these render them as a terse "MMM YYYY". A null end date
 * on a source means it is ongoing, rendered "Present" per the source data model.
 * UTC is pinned so a day string never shifts a month across the local timezone.
 */

export function formatMonthYear(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
}

/** A "MMM YYYY – MMM YYYY" range; a missing end renders "Present" when a start exists. */
export function formatDateRange(
  start: string | null | undefined,
  end: string | null | undefined,
): string {
  const startLabel = formatMonthYear(start);
  const endLabel = formatMonthYear(end);
  if (!startLabel && !endLabel) return "";
  if (startLabel && !endLabel) return `${startLabel} – Present`;
  if (!startLabel && endLabel) return endLabel;
  return `${startLabel} – ${endLabel}`;
}

/** A short 'Jul 18' day label for a worklog row. */
export function formatDay(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

/** A 'Jul 18, 2026' day label carrying the year (e.g. a job application's added date). */
export function formatDayYear(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** A month bucket key ("2025-09") for grouping entries newest-month-first. */
export function monthKey(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "unknown";
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

/** A "September 2025" heading for a month bucket key. */
export function monthKeyLabel(key: string): string {
  const [year, month] = key.split("-").map(Number);
  if (!year || !month) return "Undated";
  return new Date(Date.UTC(year, month - 1, 1)).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}
