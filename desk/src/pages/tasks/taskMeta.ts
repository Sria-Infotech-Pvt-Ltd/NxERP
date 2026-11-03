import { __ } from "@/translation";
import { dayjs } from "frappe-ui";

export interface TaskUser {
  name: string;
  full_name: string;
  user_image?: string | null;
}

export interface TaskRow {
  name: string;
  subject: string;
  status: TaskStatus;
  priority: TaskPriority;
  assigned_to?: string | null;
  reviewer?: string | null;
  project?: string | null;
  milestone?: string | null;
  assignee_type?: "Employee" | "Freelancer";
  freelancer?: string | null;
  pbt_project_id?: string | null;
  pbt_project_name?: string | null;
  pbt_project_status?: string | null;
  pbt_milestone_id?: string | null;
  pbt_milestone_name?: string | null;
  pbt_assignment_id?: string | null;
  pbt_resource_type?: "employee" | "freelancer" | null;
  pbt_resource_name?: string | null;
  hrms_employee_id?: string | null;
  hrms_employee_name?: string | null;
  hrms_department?: string | null;
  hrms_designation?: string | null;
  start_date?: string | null;
  due_date?: string | null;
  progress: number;
  owner: string;
  creation: string;
  assignee?: TaskUser | null;
  reviewer_details?: TaskUser | null;
  creator?: TaskUser | null;
}

export interface ChecklistItem {
  item: string;
  done: 0 | 1;
}

export interface TaskDetail extends TaskRow {
  description?: string;
  blocked_reason?: string | null;
  milestone_name?: string | null; // title of the local milestone
  checklist: ChecklistItem[];
  attachments: { name: string; file_name: string; file_url: string }[];
  comments: {
    name: string;
    content: string;
    creation: string;
    user?: TaskUser | null;
  }[];
  activity: {
    creation: string;
    user?: TaskUser | null;
    changes: { field: string; old: unknown; new: unknown }[];
  }[];
  permissions: { write: boolean; delete: boolean };
}

export type TaskStatus =
  | "Planned"
  | "In Progress"
  | "In Review"
  | "Completed"
  | "Blocked"
  | "Cancelled";
export type TaskPriority = "Low" | "Medium" | "High" | "Urgent";
export type TaskView =
  | "my"
  | "all"
  | "overdue"
  | "due_this_week"
  | "unassigned";

export const STATUSES: TaskStatus[] = [
  "Planned",
  "In Progress",
  "In Review",
  "Completed",
  "Blocked",
  "Cancelled",
];
export const PRIORITIES: TaskPriority[] = ["Low", "Medium", "High", "Urgent"];
export const WORKFLOW_STEPS: TaskStatus[] = [
  "Planned",
  "In Progress",
  "In Review",
  "Completed",
];

export const statusTheme: Record<TaskStatus, string> = {
  Planned: "gray",
  "In Progress": "blue",
  "In Review": "violet",
  Completed: "green",
  Blocked: "orange",
  Cancelled: "gray",
};

// Indicator dot beside the status in the list, using theme ink tokens only.
export const statusDot: Record<TaskStatus, string> = {
  Planned: "text-ink-gray-5",
  "In Progress": "text-ink-blue-6",
  "In Review": "text-ink-violet-6",
  Completed: "text-ink-green-6",
  Blocked: "text-ink-orange-6",
  Cancelled: "text-ink-gray-4",
};

const CLOSED = ["Completed", "Cancelled"];

/** List filters ([field, operator, value]) behind each fixed Tasks view. `@me` is resolved server-side. */
export function viewFilters(view: TaskView): [string, string, unknown][] {
  const day = (d = dayjs()) => d.format("YYYY-MM-DD");
  if (view === "my") return [["assigned_to", "=", "@me"]];
  if (view === "unassigned") return [["assigned_to", "is", "not set"]];
  if (view === "overdue")
    return [
      ["due_date", "is", "set"],
      ["due_date", "<", day()],
      ["status", "not in", CLOSED],
    ];
  if (view === "due_this_week")
    return [
      ["due_date", "between", [day(), day(dayjs().endOf("week"))]],
      ["status", "not in", CLOSED],
    ];
  return [];
}

export const priorityBadge: Record<
  TaskPriority,
  { theme: string; variant: "subtle" | "solid" }
> = {
  Low: { theme: "green", variant: "subtle" },
  Medium: { theme: "amber", variant: "subtle" },
  High: { theme: "red", variant: "subtle" },
  Urgent: { theme: "red", variant: "solid" },
};

// frappe-ui's amber badge text (ink-amber-8) is only 3.5:1 on its tint and its solid red is 4.46:1
// with white text; these darker tokens bring every badge above 4.5:1.
export const statusBadgeClass: Record<TaskStatus, string> = {
  Planned: "",
  "In Progress": "",
  "In Review": "",
  Completed: "",
  Blocked: "!text-ink-amber-9",
  Cancelled: "",
};
export const priorityBadgeClass: Record<TaskPriority, string> = {
  Low: "",
  Medium: "!text-ink-amber-9",
  High: "",
  Urgent: "!bg-surface-red-8",
};

export function viewLabels(): Record<TaskView, string> {
  return {
    my: __("My tasks"),
    all: __("All tasks"),
    overdue: __("Overdue"),
    due_this_week: __("Due this week"),
    unassigned: __("Unassigned"),
  };
}

/** Overdue only while the task is still open: a late Completed/Cancelled task is not overdue. */
export function isOverdue(task: Pick<TaskRow, "due_date" | "status">) {
  if (!task.due_date || ["Completed", "Cancelled"].includes(task.status))
    return false;
  return dayjs(task.due_date).isBefore(dayjs(), "day");
}

export function dueLabel(task: Pick<TaskRow, "due_date" | "status">) {
  if (!task.due_date) return "";
  const due = dayjs(task.due_date);
  const formatted = due.format("D MMM");
  if (isOverdue(task)) return `${__("Overdue")} · ${formatted}`;
  if (due.isSame(dayjs(), "day")) return __("Today");
  if (due.isSame(dayjs().add(1, "day"), "day")) return __("Tomorrow");
  return formatted;
}

/** Statuses the current user may move a task to from `status`, mirroring the server rules. */
export function nextActions(status: TaskStatus) {
  const actions: { label: string; to: TaskStatus; needsReason?: boolean }[] =
    [];
  if (status === "Planned")
    actions.push({ label: __("Start task"), to: "In Progress" });
  if (status === "In Progress") {
    actions.push({ label: __("Move to review"), to: "In Review" });
    actions.push({
      label: __("Mark blocked"),
      to: "Blocked",
      needsReason: true,
    });
  }
  if (status === "Blocked")
    actions.push({ label: __("Return to in progress"), to: "In Progress" });
  if (status === "In Review") {
    actions.push({ label: __("Approve & complete"), to: "Completed" });
    actions.push({
      label: __("Return to in progress"),
      to: "In Progress",
      needsReason: true,
    });
  }
  return actions;
}
