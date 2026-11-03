# Task Management

Standalone internal work items for agents. Tasks share authentication, users, permissions, attachments, comments and
version history with the rest of Helpdesk, but have **no relationship to Tickets or Customers**: no link field, no
shared notifications, no hooks on ticket events.

## DocTypes

| DocType                  | Notes                                                                           |
| ------------------------ | ------------------------------------------------------------------------------- |
| `HD Task`                | Autoname `TASK-.####`, title field `subject`, track changes on.                 |
| `HD Task Project`        | Autoname from `project_name`. Optional grouping for tasks.                      |
| `HD Task Checklist Item` | Child table (`istable`): `item` (required), `done` (default 0).                 |
| `HD Task Milestone`      | Autoname `MS-####`. `milestone_name` and `project` (both required).             |
| `HD Task Designation`    | Autoname from `designation_name`. Master for the Add Task form's Designation.   |
| `HD Task Freelancer`     | Autoname from `freelancer_name`; optional `email`. Master for freelancer assignees. |

`HD Task` fields: `subject` (required), `description`, `status` (default Planned), `priority` (default Medium),
`assigned_to` (defaults to the creator), `reviewer`, `project`, `milestone`, `assignee_type` (Employee or Freelancer,
default Employee), `department` (an HD Team), `designation`, `freelancer`, `start_date`, `due_date`, `progress` (read-only,
server-calculated), `checklist`, `blocked_reason`, `completed_on` / `completed_by` (read-only).

External references (all optional `Data` fields, no new DocTypes; legacy fields above are unchanged):
`pbt_project_id` (the reference), `pbt_project_name`, `pbt_project_status` (raw PBT status, e.g. `uat`);
`pbt_milestone_id` (the reference, a milestone of the PBT project), `pbt_milestone_name`;
`pbt_assignment_id` (the reference, a resource assignment of the PBT project), `pbt_resource_type` (`employee` or
`freelancer`), `pbt_resource_code` (AIRA employee id / freelancer code), `pbt_resource_name`;
`hrms_employee_id` (the reference), `hrms_employee_name`, `hrms_department`, `hrms_designation`. The ids are what the
client sends; the other fields are written by the server from the external API on insert or when the id changes, so a
client cannot choose them. See "External integrations (PBT and HRMS)".

## Workflow

Statuses: Planned, In Progress, In Review, Completed, Blocked, Cancelled. A new task may be created in any status (default
Planned); the transition table below applies to changes after creation. A task created as Blocked needs a Blocked Reason, and one
created as Completed gets `completed_on` / `completed_by` and 100% progress like any other completion.

| From        | To                        |
| ----------- | ------------------------- |
| Planned     | In Progress               |
| In Progress | In Review, Blocked        |
| Blocked     | In Progress               |
| In Review   | Completed, In Progress    |
| any         | Cancelled                 |

Every other move is rejected. All rules live in `HDTask.validate`, so they apply to the UI, the whitelisted APIs,
bulk operations and any other save (`frappe.client.*`, desk form, scripts).

- **Blocked** requires `blocked_reason`; the field is cleared on any other status.
- **In Review → In Progress** (return) requires a comment, stored as a core Comment and sent to the assignee.
- **In Review → Completed / In Progress** is limited to the task's reviewer or an Agent Manager / System Manager.
  The assignee can never approve their own task.
- **Completion** sets `completed_on` / `completed_by` from the server clock and session user and forces progress to
  100. Client-sent values are discarded. Reopening clears them.
- **Progress** = done checklist items / total, rounded half-up; 0 with no checklist.
- **Assignee type**: a Freelancer task requires `freelancer` (or a PBT freelancer resource) and clears `assigned_to`,
  `department` and `designation` (and is not defaulted to the creator); an Employee task clears `freelancer`. A PBT
  resource sets the type itself (see "PBT resources").
- **Milestone** (local) must belong to the task's local project; **PBT milestone** must belong to the task's PBT project
  in PBT and needs a PBT project.
- `due_date` may not precede `start_date`; `assigned_to` and `reviewer` must be enabled users.

## Permissions

| Role           | Access                                                                    |
| -------------- | ------------------------------------------------------------------------- |
| Agent          | Create, read and write tasks they own, are assigned to or review. No delete. |
| Agent Manager  | Full access to every task, including delete.                              |
| System Manager | Full access to every task, including delete.                              |

Enforced by DocType permissions plus `permission_query` (list filtering) and `has_permission` (document check) in
`hd_task.py`, registered in `hooks.py`. The API never trusts a user id from the client; the actor is always
`frappe.session.user`.

## API (`helpdesk.api.task`)

All endpoints require an Agent, Agent Manager or System Manager.

| Endpoint                | Purpose                                                                                 |
| ----------------------- | --------------------------------------------------------------------------------------- |
| `get_tasks`             | Paginated list. `view`: my, all, overdue, due_this_week, unassigned. `filters`: status, priority, assigned_to, project, search. `page_size` is capped at 100. |
| `get_task_form_options` | Choices for the Add Task form: milestones of `project`, departments (HD Teams), designations, freelancers, and active agents (narrowed to the `department` team's members). |
| `get_pbt_projects`      | PBT projects (every page) as a read-only proxy. Optional `search`, `status`, `client_id`. |
| `get_pbt_milestones`    | Active milestones of one PBT `project_id`, in PBT's order (every page). Optional `status` (comma-separated). Unknown project: "not found" error. |
| `get_pbt_resources`     | Active employee and freelancer assignments of one PBT `project_id`, optionally on `milestone_id` (every page; vendors and external people left out). Unknown project, or a milestone outside it: "not found" error. |
| `get_hrms_employees`    | HRMS employees, each with `user`: the enabled Frappe User with the same email, else null. |
| `get_hrms_employee`     | One HRMS employee by id (same shape, 404-style error when unknown).                     |
| `get_task_counts`       | Counts for each view plus open tasks.                                                   |
| `get_task`              | One task with checklist, attachments, comments and activity.                            |
| `update_status`         | Move a task through the workflow; `reason` is the blocked reason or return comment.     |
| `update_checklist`      | Replace the checklist; progress is recalculated server-side.                            |
| `add_comment`           | Add a comment (mentions are restricted to users who can access the task).               |
| `get_mentionable_users` | Users who may be mentioned on a task.                                                   |
| `bulk_assign`           | Assign many tasks. Each task is processed in its own savepoint; failures are reported per task. |
| `bulk_update_status`    | Same, for status changes.                                                               |

## Notifications

In-app only, through Frappe's `Notification Log` (not the Ticket `HD Notification`), best effort and never failing the
task operation. Nobody is notified of their own action.

- Assigned (on create and on reassignment) to the assignee.
- Returned from review, with the reviewer's comment, to the assignee.
- Overdue, to the assignee.

### Scheduler

`helpdesk.helpdesk.doctype.hd_task.hd_task.notify_overdue_tasks` runs daily (`scheduler_events["daily"]`). It finds
open tasks past their due date and sends one overdue notification per task per due date (the subject carries the due
date, so a moved due date can notify again).

## Frontend

The Tasks list uses the same generic list as Tickets (`ListViewBuilder` with `useView("HD Task")`), so it has the
Refresh / Filter / Sort / Columns controls, the 20 / 50 / 100 page-size footer and saved, private and public views.
The quick-filter inputs (ID, Subject, Status, Priority, Assigned To) are hidden (`hideQuickFilters`); filtering is
through the Filter button.

- Routes: `/helpdesk/tasks` (list) and `/helpdesk/tasks/:taskId` (detail page, `TaskPage.vue` reusing `TaskDetail.vue`).
  Sidebar entry **Tasks** directly after Contacts (`layoutSettings.ts`).
- Opening a task: clicking a row opens `TaskDetail` in a side panel next to the list (`?task=<name>` on the URL, so Back,
  refresh and shared links keep it open). Below `lg` the panel covers the list. The row link is replaced through the
  `onRowClick` option of `ListViewBuilder`, which also stops a cell click from applying a filter. The open row's subject
  is bold. Status changes in the panel reload the list. `/helpdesk/tasks/:taskId` still works as a full page.
- No default filter: the Tasks list always starts unfiltered. `skipDefaultViewFilters` ignores filters saved on the user's
  default `HD View` and stops saving new ones there, because a one-off Status filter would otherwise become the landing
  state. Sort and columns are still saved.
- Columns: `default_list_data` widths are proportional (`minmax(0, Nfr)`) so the list fits its width with no horizontal
  scrollbar.
- Header: breadcrumb `Tasks / List` with the view dropdown, and a **Create** button that opens `NewTaskDialog` (titled Add Task). Field order: Task Title (required), Project, Milestone
  (follows the project), an Employee/Freelancer switch and the matching Select Employee / Select Freelancer, then Status
  (all six, default Planned; Blocked shows a required Blocked reason), Start Date and End Date (both **required**; End
  Date is stored as `due_date` and may not precede the start). It saves with `create_task`, which also rejects a missing
  date (422). There is no Allocated Hours field, and no Department / Designation filters (removed 2026-11-03).
  **Assignee for a PBT project**: the Employee / Freelancer list is the project's active PBT resources of that type
  (`get_pbt_resources`): the whole project until a milestone is picked, then that milestone's resources, as PBT
  suggests. Each option is one assignment (label: name, plus the code when a name repeats; meta: role · milestone · code)
  and is sent as `pbt_assignment_id`; changing the project, milestone or Employee/Freelancer tab clears it, and a late
  answer for an earlier project or milestone is ignored. Hints cover an empty list, an employee with no AIRA id in PBT,
  and an employee whose HRMS record has no Help Desk user. A Freelancer is required there too.
  **Assignee otherwise** (local project or none): Select Employee is the full HRMS list and Select Freelancer the local
  `HD Task Freelancer`s.
  **Project** lists PBT projects (value `pbt:<project_id>`) followed by existing local `HD Task Project`s marked
  "(local)" (value `local:<name>`). **Milestone** follows the project: for a PBT project it is loaded from
  `get_pbt_milestones` when the project is chosen (label `name (status)`, sent as `pbt_milestone_id`; "This project has no
  milestones in PBT" when empty, and a separate "Could not load PBT milestones" error that does not block saving); for a
  local project it lists that project's `HD Task Milestone`s (sent as `milestone`). Changing the project clears the
  milestone, and a late answer for a previously selected project is ignored. The task page shows the milestone under
  Project (`get_task` adds `milestone_name` for a local one), and a PBT resource without a Help Desk user by its PBT
  name. The form never sends `assigned_to` for an HRMS employee or PBT resource. See "External integrations (PBT and
  HRMS)".
- Default views (frontend only, no saved records): All tasks, My tasks, Overdue, Due this week, Unassigned. Each puts its
  filters on the URL (`?tview=...&filters=[...]`), see `viewFilters` in `taskMeta.ts`. `@me` is resolved server-side.
- Select banner: **Assign** and **Status** (`TaskBulkDialog.vue`, calling `bulk_assign` / `bulk_update_status`), plus the
  list's standard Delete for managers.
- Files: `desk/src/pages/tasks/`: `Tasks.vue`, `TaskPage.vue`, `TaskDetail.vue`, `NewTaskDialog.vue`,
  `TaskBulkDialog.vue`, `TaskReasonDialog.vue`, `TaskUser.vue`, `taskMeta.ts`.
- `useView` returns to the list the user is on after creating or deleting a view (it used to assume Tickets).

### List configuration

- Default columns come from `HDTask.default_list_data` (ID, Subject, Status, Due Date, PBT Project, Employee);
  the generic list does not read `in_list_view`. Priority, Assigned To and the local Project were dropped from the
  defaults on request; users can still add them back with the Columns button.
- Quick filters come from `in_standard_filter` on `subject`, `status`, `priority`, `assigned_to` and `project`, plus ID
  (`api/doc.py`, marked `# HD Task module`).
- `get_task_counts` is kept in the API but the list page no longer calls it.

## External integrations (PBT and HRMS)

Status: **both verified against the live servers on 2026-11-03** (taskdev stack, LAN hosts, development keys): the
proxies return the PBT projects and HRMS employees, and a task saved with a PBT project and an HRMS employee passes both
live lookups and gets its server-written fields. HRMS was seen to drop off the network for a minute or two at a time;
the form then shows its "did not respond in time" error while PBT keeps working, and the reverse.

- Code: `helpdesk/integrations/external/` with `client.py` (shared HTTP helper that takes the variable names per
  service, so PBT and HRMS never share a key), `pbt.py`, `hrms.py` and `mapping.py` (email to User). Proxies are in
  `helpdesk/api/task.py`; the checks on save are in `HDTask.validate_pbt_project` / `validate_pbt_milestone` /
  `validate_pbt_resource` / `validate_hrms_employee`.
- Configuration, read from the environment first, then `site_config.json`: `PBT_API_BASE_URL`, `PBT_API_KEY`,
  `HRMS_API_BASE_URL`, `HRMS_API_KEY`. Keys are only sent as the `X-API-Key` header, never to the browser, and never
  appear in error messages. Both `docker/nxerp/compose.yaml` and `compose.taskdev.yaml` pass the four variables to the
  `backend` service only (not to `frontend`). An unset service answers "not configured".
- Requests use a 3 s connect / 10 s read timeout and normal TLS verification. HTTP 429 is retried once when the wait
  (`retry_after_seconds`, else `Retry-After`) is 5 s or less; 400 / 401 / 403 / 429 / other errors become short,
  translated messages.
- **PBT**: `GET /api/v1/projects/` in the documented envelope; all pages are fetched (capped at 50). There is no detail
  endpoint, so a project is verified with the `project_id` filter and an exact id match. Projects are never copied into
  `HD Task Project`. Budget, invoice and contact data are not in the API and are not stored. The live API matches the
  envelope; `project_id` arrives as an integer and is kept as a string, the `project_id` filter returns the exact
  project, and rows also carry `created_at` / `updated_at`, which are not used.
- **PBT milestones**: `GET /api/v1/projects/<project_id>/milestones/` (same key), envelope `data: {project_id,
  project_name, count, page, page_size, total_pages, results}`; rows `milestone_id` (integer, kept as a string),
  `milestone_name`, `sequence`, `status` (`not_started`, `in_progress`, `completed`, `on_hold`, `cancelled`),
  `status_display`, `start_date`, `end_date`, `completion_percent`. PBT returns only active milestones in their set order
  (archived ones are left out); a project without milestones (usually time-and-material) gives an empty list. All pages
  are fetched (capped at 50). Unknown project: 404, which `pbt.get_milestones` returns as None (proxy: "not found");
  other errors raise. The project id must be a plain token before it goes into the URL path. There is no detail
  endpoint, so a milestone is verified by an exact id match in its project's list. Milestones are never copied into
  `HD Task Milestone`. Checked live on 2026-11-03 (14 milestones across 8 of the 14 projects).
- **PBT resources**: `GET /api/v1/projects/<project_id>/resources/` (same key), same envelope; filters `milestone_id`,
  `resource_type` (`employee`, `freelancer`, `vendor`, `external`) and `status` (`active`, `completed`, `on_hold`,
  `removed`; PBT leaves out `removed` by default). Rows: `assignment_id` and `milestone_id` (integers, kept as strings;
  `milestone_id` null for time-and-material rows, which come first), `resource_type`, `resource_code`, `resource_name`,
  `role`, `milestone_name`, dates, `allocation_percent`, `status`. One row per assignment, so a person on two milestones
  appears twice. Unknown project, or a `milestone_id` outside it: 404, returned as None. The proxy asks for
  `status=active` and keeps only employees and freelancers. Resources are never copied into a local DocType.
  On save, `HDTask.validate_pbt_resource` re-reads the assignment (exact `assignment_id` match in the project, narrowed to
  the task's PBT milestone) when the project, milestone or assignment changes, rejects vendors / external people and
  assignments outside the project or milestone, and writes type, code and name from PBT (client values are discarded;
  unchanged, they are kept from the saved task). A freelancer resource makes the task a Freelancer task with no local
  `freelancer` and no `assigned_to`. An employee resource makes it an Employee task with `hrms_employee_id` = its
  `resource_code`, so the HRMS lookup and email-to-user mapping below apply; **when PBT has no `resource_code` the task
  only records the PBT name** (no HRMS link, no `assigned_to`). Assigning such a task to a Help Desk user directly clears
  the PBT resource, like the HRMS employee. Live on 2026-11-03: 10 active assignments across 7 projects (7 employee, 3
  freelancer); **5 of the 7 employee assignments had no `resource_code`** in PBT, so they cannot be linked to HRMS until
  PBT fills it in.
- **PBT and HRMS employee ids do not match** (seen live on 2026-11-03): PBT sends codes like `EMP00081`, while HRMS
  now keys the same person by a numeric `employee_id` (`10000002`) and answers 404 for the EMP code. Earlier the same
  day HRMS accepted the EMP code (TASK-0001 was linked with it), so the HRMS id scheme changed upstream. Because PBT
  owns project assignments, a PBT employee whose code HRMS does not know is **not** an error: `unlink_hrms_employee`
  saves the task with the PBT name only (no HRMS link, no `assigned_to`), like a resource with no code. An HRMS
  employee picked directly (non-PBT project) still fails with "Employee X was not found in HRMS". Linking these
  people again needs PBT and HRMS to agree on one id (PBT sending the HRMS `employee_id`, or HRMS exposing the EMP
  code).
- **HRMS**: the live list response is `{"status", "message", "data": {"count", "page", "page_size", "total_pages",
  "results": [...]}}`, each row with `employee_id`, `full_name`, `email`, `department`, `designation`, `is_active` (plus
  fields we do not use, e.g. `phone`, `branch`, `employment_type`). The existing `FIELD_CANDIDATES` / `LIST_KEYS` in
  `hrms.py` already match it. The detail endpoint uses the same envelope with the row in `data`. An unknown id is a 404
  (`"No employee found with that employee_id."`); `hrms.get_employee` turns that 404 into "not found", so saving says
  "Employee X was not found in HRMS" instead of a generic HRMS error, while other failures still raise. Some employees
  have an empty `department` in HRMS itself; it is stored empty. The list API has no known search or filter.
- **Validation on save**: `pbt_project_id` / `pbt_milestone_id` / `hrms_employee_id` are looked up only when new or
  changed, so editing an existing task never depends on the external servers. An unknown id, or an unreachable server,
  rejects the save. A task may not have both `project` and `pbt_project_id`. A PBT milestone is re-checked when either
  the project or the milestone changes, so moving a task to another PBT project with the old milestone is rejected;
  while both are unchanged its name is kept from the saved task (a client-sent name is discarded). A local `milestone`
  still requires a local project, so it cannot be combined with a PBT project.
- **Employee to user**: `assigned_to` is set only when an enabled User has the same email as the HRMS employee. An id is
  never treated as a user id and no user is created. An unmapped employee leaves `assigned_to` empty (the creator is not
  substituted), so the task is not in anyone's My tasks, nobody is notified, and only the creator and managers can open
  it. Assigning the task to a Help Desk user directly later clears the HRMS employee. Freelancer tasks clear it too.
- The generic list has two default columns, **PBT Project** and **Employee** (`default_list_data`), which show the
  external references.

## Task API for PBT (inbound)

PBT fetches the Help Desk tasks of its projects from `helpdesk/api/pbt_inbound.py`, the mirror of PBT's own external
API (added 2026-11-03).

- `GET /api/method/helpdesk.api.pbt_inbound.get_tasks`, header `X-API-Key: <key>`. Guest-whitelisted (no Help Desk
  login); the key is compared in constant time against `PBT_INBOUND_API_KEYS` (environment first, then
  `site_config.json`; comma-separated so a key can be rotated). Missing, wrong, or no keys configured: 401
  `"Invalid or inactive API key."`. Rate limit: 120 requests a minute per IP. Read-only; GET only.
- Filters (all optional): `project_id` (PBT project; without it, every task linked to any PBT project), `milestone_id`,
  `status` (comma-separated Help Desk statuses: Planned, In Progress, In Review, Completed, Blocked, Cancelled),
  `updated_since` (ISO date or date-time, compared with the task's last change), `page`, `page_size` (default 20, max
  100). An invalid value is a 400 with a message. An unknown `project_id` is not an error: it has no tasks.
- Response, PBT's envelope returned as-is (not Frappe's `{"message": ...}` wrapper): `{"status": "success", "message":
  "Tasks retrieved.", "data": {"project_id", "time_zone", "count", "page", "page_size", "total_pages", "results"}}`.
  Rows are ordered oldest change first, so `updated_since` plus paging is a stable sync. Each row: `task_id`, `subject`,
  `status`, `priority`, `progress`, `project_id`, `project_name`, `milestone_id`, `milestone_name`, `assignment_id`,
  `resource_type`, `resource_code`, `resource_name`, `hrms_employee_id`, `hrms_employee_name`, `start_date`, `end_date`
  (= `due_date`), `completed_on`, `created_at`, `updated_at`, `url`. Dates and date-times are ISO 8601 in the Help Desk
  time zone given as `data.time_zone`. No description, comments or user emails are exposed.
- Only tasks with a `pbt_project_id` are visible; local-project tasks never are.
- Docker: both compose files pass `PBT_INBOUND_API_KEYS` to `backend` only. The taskdev key lives in its env file
  outside the repo and is given to the PBT developer privately.

## Migration note

The new external-reference fields need `bench migrate` (adds thirteen nullable `varchar` columns, including
`pbt_milestone_id` / `pbt_milestone_name` and the four `pbt_assignment_id` / `pbt_resource_*` fields, and two indexes to
`tabHD Task`; no data is rewritten).


The status `Open` was renamed `Planned`; patch `rename_task_open_status_to_planned` updates existing tasks so they stay
saveable.

## Running the tests

Tests need a throwaway site, never the live one:

```bash
bench --site <test-site> run-tests --module helpdesk.api.test_task
```

The module also asserts ticket independence: no `ticket`, `customer` or `reference_ticket` field exists, a task
lifecycle leaves tickets unchanged, and creating a ticket creates no tasks.

## Build and deploy

The local frontend cannot resolve `@framework/ui` outside a bench, so build in Docker:

```bash
docker/nxerp/build-local-image.sh <image-tag>   # base image + working-tree changes, frontend rebuilt
```

Then point `IMAGE` in `docker/nxerp/.env` at the tag, `docker compose -p nxerp-helpdesk --env-file .env up -d`, and run
`bench --site <site> migrate` (only needed when the DocTypes are not yet on the site) followed by `clear-cache`.
