export const statusColorMap = {
  Completed: "green",
  Busy: "amber",
  Failed: "red",
  Initiated: "gray",
  Queued: "gray",
  Canceled: "gray",
  Ringing: "gray",
  "No Answer": "red",
  "In Progress": "blue",
};

export const statusLabelMap = {
  Completed: "Completed",
  Initiated: "Initiated",
  Busy: "Declined",
  Failed: "Failed",
  Queued: "Queued",
  Canceled: "Canceled",
  Ringing: "Ringing",
  "No Answer": "Missed Call",
  "In Progress": "In Progress",
};

// Spelt out so Tailwind's scanner sees every class. Keys are the values of
// statusColorMap, which stays bare because the list view feeds it to a Badge
// as a theme.
export const statusTextColorMap: Record<string, string> = {
  green: "text-ink-green-7",
  amber: "text-ink-amber-7",
  red: "text-ink-red-7",
  gray: "text-ink-gray-5",
  blue: "text-ink-blue-7",
};
