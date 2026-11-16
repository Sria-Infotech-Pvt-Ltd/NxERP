import { __ } from "@/translation";
import { dayjs, type Dayjs } from "frappe-ui";
import { onMounted, onUnmounted, ref } from "vue";

/**
 * Gmail-style timestamps for the agent ticket and task pages: "Wed, Nov 11, 6:30 AM (1 day ago)".
 * The customer portal keeps its own relative "3 days ago" format (utils.ts timeAgo) and does not use this.
 *
 * Server timestamps are naive strings in the SYSTEM time zone; they are shown in the logged-in user's
 * Frappe time zone (falling back to the system zone), never the browser's.
 */

export interface TimeZones {
  system?: string | null;
  user?: string | null;
}

type ZonedDayjs = (value: string, zone: string) => Dayjs;

/** The zones the app booted with (`window.timezone`, also what frappe-ui is configured with). */
export function appTimeZones(): TimeZones {
  const zones = (window as unknown as { timezone?: TimeZones }).timezone;
  return { system: zones?.system, user: zones?.user };
}

/** The zone times are shown in: the user's, else the system's, else the browser's as a last resort. */
export function displayZone(zones: TimeZones = appTimeZones()): string {
  return (
    zones.user ||
    zones.system ||
    Intl.DateTimeFormat().resolvedOptions().timeZone
  );
}

/** Re-express a server timestamp (system time) in the user's zone. */
export function toUserTime(value: string, zones: TimeZones = appTimeZones()): Dayjs {
  // Without a system zone there is nothing to convert from: keep dayjs's default parse.
  if (!zones.system) return dayjs(value);
  return (dayjs as unknown as { tz: ZonedDayjs }).tz(value, zones.system).tz(displayZone(zones));
}

function nowInUserZone(zones: TimeZones, now?: Dayjs | Date | number): Dayjs {
  const base = now == null ? dayjs() : dayjs(now);
  return zones.system ? base.tz(displayZone(zones)) : base;
}

const plural = (n: number, one: string, many: string) =>
  n === 1 ? __(one, [n]) : __(many, [n]);

/** just now / N minutes / N hours / N days / N months / N years ago (singular for 1). */
export function relativeAgo(then: Dayjs, now: Dayjs): string {
  const seconds = now.diff(then, "second");
  // A timestamp a little ahead of this browser's clock still reads as "just now".
  if (seconds < 60) return __("just now");
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return plural(minutes, "{0} minute ago", "{0} minutes ago");
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return plural(hours, "{0} hour ago", "{0} hours ago");
  const days = now.diff(then, "day");
  if (days < 30) return plural(days, "{0} day ago", "{0} days ago");
  const months = Math.max(1, now.diff(then, "month"));
  if (months < 12) return plural(months, "{0} month ago", "{0} months ago");
  const years = Math.max(1, now.diff(then, "year"));
  return plural(years, "{0} year ago", "{0} years ago");
}

/** "Wed, Nov 11, 6:30 AM (1 day ago)"; the year is added when it is not the current one. */
export function formatGmailDate(
  value: string,
  options: { now?: Dayjs | Date | number; zones?: TimeZones } = {}
): string {
  const zones = options.zones ?? appTimeZones();
  const then = toUserTime(value, zones);
  const now = nowInUserZone(zones, options.now);
  const pattern =
    then.year() === now.year() ? "ddd, MMM D, h:mm A" : "ddd, MMM D, YYYY, h:mm A";
  return `${then.format(pattern)} (${relativeAgo(then, now)})`;
}

/** Hover text: the full date and time with the zone, e.g. "Wednesday, November 11, 2026, 6:30:12 AM · Asia/Kolkata (UTC+05:30)". */
export function formatFullDateTime(value: string, zones: TimeZones = appTimeZones()): string {
  const then = toUserTime(value, zones);
  return `${then.format("dddd, MMMM D, YYYY, h:mm:ss A")} · ${displayZone(zones)} (UTC${then.format("Z")})`;
}

// One shared timer for every date on the page: it ticks once a minute while any is mounted.
const minuteTick = ref(Date.now());
let watchers = 0;
let timer: number | undefined;

/** A ref that changes every minute, so relative times refresh without a reload. */
export function useMinuteClock() {
  onMounted(() => {
    minuteTick.value = Date.now();
    if (watchers++ === 0) {
      timer = window.setInterval(() => (minuteTick.value = Date.now()), 60_000);
    }
  });
  onUnmounted(() => {
    if (--watchers === 0 && timer !== undefined) {
      window.clearInterval(timer);
      timer = undefined;
    }
  });
  return minuteTick;
}
