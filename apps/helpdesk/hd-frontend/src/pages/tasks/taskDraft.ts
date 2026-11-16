import { reactive } from "vue";

/** A task being created: the Create Task form fills it, the description page completes and submits it. */
export interface TaskDraft {
  subject: string;
  project: string; // "pbt:<project_id>" or "local:<HD Task Project name>", as in the form
  milestone: string;
  assignee_type: "Employee" | "Freelancer";
  hrms_employee_id: string; // HRMS employee id; "" unless assignee_type is Employee
  freelancer: string; // HD Task Freelancer name; "" unless assignee_type is Freelancer
  status: string;
  blocked_reason: string; // only meaningful while status is Blocked
  start_date: string;
  due_date: string;
  description: string; // editor HTML
  // Shown on the description page only; the server re-reads names from the ids.
  projectLabel: string;
  milestoneLabel: string;
  assigneeLabel: string;
  // One id per draft: the server returns the same task if a create is sent twice.
  requestId: string;
}

// Module state, not the URL: nothing the user typed should end up in a link or the browser history.
export const taskDraft = reactive<{ value: TaskDraft | null; reopen: boolean }>({
  value: null,
  reopen: false,
});

export const newRequestId = () =>
  globalThis.crypto?.randomUUID?.() ??
  `${Date.now()}-${Math.random().toString(36).slice(2)}`;

export function clearTaskDraft() {
  taskDraft.value = null;
  taskDraft.reopen = false;
}
