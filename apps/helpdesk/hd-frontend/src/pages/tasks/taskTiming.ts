import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import type { TaskStatus } from "./taskMeta";

export type TimingTone = "muted" | "normal" | "warning" | "danger";

export interface Timing {
  text: string;
  tone: TimingTone;
  /** The exact date, for the info icon; empty when the date is not set. */
  exact: string;
}

const CLOSED: TaskStatus[] = ["Completed", "Cancelled"];

const short = (date: string) => dayjs(date).format("D MMM YYYY");
const exactDate = (date: string) => dayjs(date).format("dddd, D MMMM YYYY");

/** Whole days from `today` to `date`: positive when `date` is in the future. Both are site-local dates. */
function daysFrom(date: string, today: string) {
  return dayjs(date).startOf("day").diff(dayjs(today).startOf("day"), "day");
}

/** "Not set", "Starts in 3d", "Starts today" or "Started 5 Nov 2026". */
export function startTiming(start: string | null | undefined, today: string): Timing {
  if (!start) return { text: __("Not set"), tone: "muted", exact: "" };
  const days = daysFrom(start, today);
  const exact = exactDate(start);
  if (days > 0) return { text: __("Starts in {0}d", [days]), tone: "normal", exact };
  if (days === 0) return { text: __("Starts today"), tone: "normal", exact };
  return { text: __("Started {0}", [short(start)]), tone: "normal", exact };
}

/** "Not set", "Due in 3d", "Due today" (warning), "Overdue by 2d" (danger). A closed task just shows its date. */
export function dueTiming(
  due: string | null | undefined,
  status: TaskStatus,
  today: string
): Timing {
  if (!due) return { text: __("Not set"), tone: "muted", exact: "" };
  const exact = exactDate(due);
  if (CLOSED.includes(status)) return { text: short(due), tone: "normal", exact };
  const days = daysFrom(due, today);
  if (days > 0) return { text: __("Due in {0}d", [days]), tone: "normal", exact };
  if (days === 0) return { text: __("Due today"), tone: "warning", exact };
  return { text: __("Overdue by {0}d", [-days]), tone: "danger", exact };
}

/** Same tokens the ticket's SLA rows use. */
export const timingToneClass: Record<TimingTone, string> = {
  muted: "text-ink-gray-5",
  normal: "text-ink-gray-7",
  warning: "text-ink-amber-8",
  danger: "text-ink-red-7",
};
