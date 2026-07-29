/**
 * Calendar-date helpers for `performed_on` / `recorded_on`.
 *
 * The backend deliberately stores these as SQL DATE, not a timestamp: a workout
 * belongs to a calendar day in the user's own timezone (see the comment on
 * `Workout.performed_on`). The frontend has to honour that same rule, and the
 * obvious code does not:
 *
 *   new Date("2026-07-26")            // -> 2026-07-26T00:00:00 **UTC**
 *   ...rendered west of UTC           // -> "Jul 25". Off by one.
 *
 * So we never hand a bare `YYYY-MM-DD` to the Date constructor. Everything here
 * works in local time, which is what the user means by "today".
 */

/** Parse `YYYY-MM-DD` as midnight *local* time. */
export function parseLocalDate(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

/** Format a Date as `YYYY-MM-DD` using its *local* fields. */
export function toISODate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/** Today, in the user's timezone. The default date for a new workout. */
export function todayISO(): string {
  return toISODate(new Date());
}

/** Whole days from `iso` to today. Positive = in the past. */
export function daysAgo(iso: string): number {
  const then = parseLocalDate(iso).getTime();
  const now = parseLocalDate(todayISO()).getTime();
  return Math.round((now - then) / 86_400_000);
}

/** `YYYY-MM-DD` for the Monday of the current week. */
export function startOfWeekISO(): string {
  const now = new Date();
  // getDay(): 0 = Sunday. Shift so Monday is the first day.
  const offset = (now.getDay() + 6) % 7;
  now.setDate(now.getDate() - offset);
  return toISODate(now);
}

/**
 * Every Monday from `startISO` to `endISO` inclusive, as `YYYY-MM-DD`.
 *
 * The analytics API omits weeks with no training rather than zero-filling them —
 * it cannot tell "rested" from "outside the window", but the caller knows the
 * window, so the axis is built here. Without this a three-week layoff would
 * silently close up and the chart would read as unbroken training.
 */
export function weeksBetween(startISO: string, endISO: string): string[] {
  const end = parseLocalDate(endISO);
  const cursor = parseLocalDate(startISO);
  const weeks: string[] = [];
  // Guard rather than trust: a bad range must not spin forever in a render.
  while (cursor <= end && weeks.length < 106) {
    weeks.push(toISODate(cursor));
    cursor.setDate(cursor.getDate() + 7);
  }
  return weeks;
}

/** "Mon, 26 Jul 2026" — the long form, for detail headers. */
export function formatLongDate(iso: string): string {
  return parseLocalDate(iso).toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** "26 Jul" — the compact form, for list rows. */
export function formatShortDate(iso: string): string {
  return parseLocalDate(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
}

/** "Today" / "Yesterday" / "3 days ago" / a date, whichever reads best. */
export function formatRelativeDay(iso: string): string {
  const diff = daysAgo(iso);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff === -1) return "Tomorrow";
  if (diff > 1 && diff < 7) return `${diff} days ago`;
  return formatLongDate(iso);
}
