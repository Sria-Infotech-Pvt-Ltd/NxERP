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
| `HD Task Designation`    | Autoname from `designation_name`. Master for the task form's Designation.   |
| `HD Task Freelancer`     | Autoname from `freelancer_name`; optional `email`. Master for freelancer assignees. |

`HD Task` fields: `subject` (required), `description`, `status` (default Planned), `priority` (default Medium),
`assigned_to` (defaults to the creator), `reviewer`, `project`, `milestone`, `assignee_type` (Employee or Freelancer,
default Employee), `department` (an HD Team), `designation`, `freelancer`, `start_date`, `due_date`, `progress` (read-only,
server-calculated), `checklist`, `blocked_reason`, `completed_on` / `completed_by` (read-only).

External references (all optional `Data` fields, no new DocTypes; legacy fields above are unchanged):
`pbt_project_id` (the reference), `pbt_project_name`, `pbt_project_status` (raw PBT status, e.g. `uat`);
`hrms_employee_id` (the reference), `hrms_employee_name`, `hrms_department`, `hrms_designation`. The id is what the
client sends; the other five are written by the server from the external API on insert or when the id changes, so a
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
- **Assignee type**: a Freelancer task requires `freelancer` and clears `assigned_to`, `department` and `designation`
  (and is not defaulted to the creator); an Employee task clears `freelancer`.
- **Milestone** must belong to the task's project.
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

All endpoints require an Agent, Agent Manager or System Manager. Read endpoints accept GET and POST; write endpoints are POST-only.

| Endpoint                | Purpose                                                                                 |
| ----------------------- | --------------------------------------------------------------------------------------- |
| `get_tasks`             | Paginated list. `view`: my, all, overdue, due_this_week, unassigned. `filters`: status, priority, assigned_to, project, search. `page_size` is capped at 100. |
| `get_task_form_options` | Choices for the New task form: milestones of `project`, departments (HD Teams), designations, freelancers, and active agents (narrowed to the `department` team's members). |
| `get_pbt_projects`      | PBT projects (every page) as a read-only proxy. Optional `search`, `status`, `client_id`. |
| `get_hrms_employees`    | HRMS employees, each with `user`: the enabled Frappe User with the same email, else null. |
| `get_hrms_employee`     | One HRMS employee by id (same shape, 404-style error when unknown).                     |
| `get_task_counts`       | Counts for each view plus open tasks.                                                   |
| `get_task`              | One task with checklist, attachments, comments and activity. Also `allowed_statuses` (the statuses this user may move it to now, computed by the same helpers as `HDTask.validate`) and `today` (the site's date). |
| `update_task_fields`    | Save sidebar edits: only `priority`, `reviewer`, `project`, `pbt_project_id`, `milestone`, `start_date`, `due_date` (anything else is refused). Write access required; saved with `doc.save()`, so `HDTask.validate` checks every rule. Returns the whole task, or `{access_lost: true}` when the edit took away the caller's own access. |
| `update_status`         | Move a task through the workflow; `reason` is the blocked reason or return comment.     |
| `update_checklist`      | Replace the checklist; progress is recalculated server-side.                            |
| `add_comment`           | Add a comment (mentions are restricted to users who can access the task).               |
| `reply_via_email`       | Email a reply about the task (write access). Validates To/Cc/Bcc, throws "No outgoing email account is configured" before writing anything, stores a `Communication` linked to the task (`Sent`) and queues the email. `get_task` also returns `emails` (those Communications) and `reply_recipients` (assignee and reviewer emails). |
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
The quick-filter inputs sit left of the Refresh / Filter / Sort / Columns buttons, as on Tickets: **ID**, **Subject**
(both "like" matches) and **Assigned To** (a dropdown of enabled users with the Agent role). They combine with the default
views, the Filter button and paging. A quick filter on Assigned To replaces the assignee condition of the My and Unassigned
views (same behaviour as every quick filter on the Tickets list). Everything else is filtered through the Filter button.

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
- Header: breadcrumb `Tasks / List` with the view dropdown, and a **Create** button that opens `NewTaskDialog` (titled New task; its button is **Assigned**). Field order: Task Title (required), Project, Milestone
  (follows the project), an Employee/Freelancer switch, then for Employee Select Employee (disabled with "Select project
  first" until a project is chosen; changing the project clears it and the milestone), or for Freelancer a Select Freelancer dropdown,
  then Status (all six, default Planned; Blocked shows a required Blocked reason), Start Date and End Date (stored as
  `due_date`; may not precede the start). **Assigned** validates Task Title and the assignee (Select Employee, or Select Freelancer when that switch is active), with inline errors
  that clear on edit, then saves the form into the module-level draft (`taskDraft.ts`), closes the dialog and goes to
  `/helpdesk/tasks/new`. Nothing is created there. The task is created only by **Submit** on that page. There is no Allocated Hours field.
  **New task page** (`TaskNew.vue`): breadcrumb `Tasks / New task`; a read-only summary of the draft (project, milestone,
  assignee and type, status, due date) with **Edit** (or **Assign** when nobody is chosen), which reopens the dialog prefilled
  from the draft and, on **Assigned**, updates the draft without navigating; a **Subject** input (placeholder "A short
  description", max 140) prefilled from the title; and the ticket composer (`TicketTextEditor`) bound to the draft
  description. Attach, image and video are hidden (`hide-uploads`), because uploads would attach to a task that does not
  exist yet. **Submit** requires a Subject, then calls `create_task` with the draft and a per-draft `request_id` (a retry
  returns the task already created); on success it clears the draft, toasts "Task created" and replaces the route with
  `/helpdesk/tasks/:taskId`; on error it shows the server message and keeps the draft. Opening `/helpdesk/tasks/new` with no
  draft (or after a reload) starts an empty draft and shows "Not assigned"; the server still decides what is valid, and an
  Employee task with no employee defaults to the creator as before.
  **Project** lists PBT projects (value `pbt:<project_id>`) followed by existing local `HD Task Project`s marked
  "(local)" (value `local:<name>`); **Milestone** is only enabled for a local project, because milestones exist only for
  those. **Select Employee** comes from HRMS and lists every HRMS employee: there is no project or milestone team data
  yet (not in HD Task Project, HD Task Milestone or the PBT contract), so the list is not narrowed by project. The form has no
  Department or Designation field; the `department` / `designation` fields stay on `HD Task` for existing records. The form never sends `assigned_to` for an
  HRMS employee. See "External integrations (PBT and HRMS)". Freelancers still come from `HD Task Freelancer`.
- Default views (frontend only, no saved records): All tasks, My tasks, Overdue, Due this week, Unassigned. Each puts its
  filters on the URL (`?tview=...&filters=[...]`), see `viewFilters` in `taskMeta.ts`. `@me` is resolved server-side.
- Select banner: **Assign** and **Status** (`TaskBulkDialog.vue`, calling `bulk_assign` / `bulk_update_status`), plus the
  list's standard Delete for managers.
- Files: `desk/src/pages/tasks/`: `Tasks.vue`, `TaskPage.vue`, `TaskDetail.vue`, `NewTaskDialog.vue`,
  `TaskBulkDialog.vue`, `TaskReasonDialog.vue`, `TaskUser.vue`, `taskMeta.ts`.
- `useView` returns to the list the user is on after creating or deleting a view (it used to assume Tickets).

### List configuration

- Default columns come from `HDTask.default_list_data` (ID, Subject, Status, Priority, Assigned To, Due Date, Project);
  the generic list does not read `in_list_view`. Users change columns with the Columns button.
- Quick filters come from `in_standard_filter` on `subject` and `assigned_to` in `hd_task.json`, plus ID (`api/doc.py`,
  marked `# HD Task module`). `assigned_to` is a Link to User, which would offer everyone, so `get_quick_filters` turns it into
  a Select whose choices come from `HDTask.assignee_filter_options` (enabled System Users holding the Agent role; nobody
  who cannot list tasks gets any). Filtering is the generic `get_list_data` -> `frappe.get_list`, so the `HD Task`
  `permission_query` still applies: a filter can only narrow what the agent may already see.
- **Assigned To column**: a Freelancer task has no `assigned_to` user, so `get_list_data` also loads `assignee_type` and
  `freelancer`, and `HDTask.add_freelancer_names` adds `freelancer_name` to each row (`get_tasks` does the same). The cell shows
  the freelancer's name with a small "Freelancer" hint, as the task sidebar does.
- `get_task_counts` is kept in the API but the list page no longer calls it.

## External integrations (PBT and HRMS)

Status: **code prepared, not verified against the live servers** (both timed out from the backend container and the
Windows host on 2026-10-30). Everything is tested with mocked responses only.

- Code: `helpdesk/integrations/external/` with `client.py` (shared HTTP helper that takes the variable names per
  service, so PBT and HRMS never share a key), `pbt.py`, `hrms.py` and `mapping.py` (email to User). Proxies are in
  `helpdesk/api/task.py`; the checks on save are in `HDTask.validate_pbt_project` / `validate_hrms_employee`.
- Configuration, read from the environment first, then `site_config.json`: `PBT_API_BASE_URL`, `PBT_API_KEY`,
  `HRMS_API_BASE_URL`, `HRMS_API_KEY`. Keys are only sent as the `X-API-Key` header, never to the browser, and never
  appear in error messages. They are **not yet set** in the Docker stack.
- Requests use a 3 s connect / 10 s read timeout and normal TLS verification. HTTP 429 is retried once when the wait
  (`retry_after_seconds`, else `Retry-After`) is 5 s or less; 400 / 401 / 403 / 429 / other errors become short,
  translated messages.
- **PBT**: `GET /api/v1/projects/` in the documented envelope; all pages are fetched (capped at 50). There is no detail
  endpoint, so a project is verified with the `project_id` filter and an exact id match. Projects are never copied into
  `HD Task Project`. Milestone, budget, invoice and contact data are not in the API and are not stored.
- **HRMS** (UNVERIFIED mapping): only the URLs and header are known. `FIELD_CANDIDATES` and `LIST_KEYS` in `hrms.py`
  are guesses at the response shape and must be corrected from a real response. The list API has no known search or
  filter, so Department / Designation filtering is done on the fetched list.
- **Validation on save**: `pbt_project_id` / `hrms_employee_id` are looked up only when new or changed, so editing an
  existing task never depends on the external servers. An unknown id, or an unreachable server, rejects the save. A task
  may not have both `project` and `pbt_project_id`; the existing milestone rule still applies, so a PBT task cannot
  carry a milestone yet.
- **Employee to user**: `assigned_to` is set only when an enabled User has the same email as the HRMS employee. An id is
  never treated as a user id and no user is created. An unmapped employee leaves `assigned_to` empty (the creator is not
  substituted), so the task is not in anyone's My tasks, nobody is notified, and only the creator and managers can open
  it. Assigning the task to a Help Desk user directly later clears the HRMS employee. Freelancer tasks clear it too.
- The generic list gained two default columns, **PBT Project** and **Employee** (`default_list_data`), so tasks that use
  the external references are not blank in Project / Assigned To.

## Migration note

The new external-reference fields need `bench migrate` (adds seven nullable `varchar` columns and two indexes to
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

### Reply and Comment on the task page

Under the Activity area a bar with two toggle buttons, **Reply** and **Comment**, opens their composer; clicking the active one collapses
it (see "Composer bar" below for the open, close and draft rules). **Comment** is unchanged (`add_comment`, @mentions from `get_mentionable_users`). **Reply** (`TaskReplyComposer.vue`)
shows removable "To" chips prefilled from `reply_recipients` (the assignee's user email or the freelancer's email, plus the
reviewer's), Cc / Bcc toggles, the same toolbar as the task comment composer, **Discard** (clears the text and puts the
recipients back) and **Send (Ctrl+Enter)**. It calls `reply_via_email`; on any error, including a site with no outgoing
Email Account, the message is shown and the text stays in the editor. Sent replies show in the Activity timeline and on the
Emails tab. Reply is disabled for users without write access to the task. Attachments are hidden in this composer: a file
would have to be linked to the task and to the email at send time, which is not built yet. The composer reuses
`EmailMultiSelect` and the editor config from the ticket page unchanged; no ticket file is involved.

### Frontend build check

`npm run build` in `hd-frontend` cannot run on a host checkout: `package.json` links `@framework/ui` to `../../frappe/ui`,
which exists only inside a bench (error: `Cannot find package '@framework/ui'`). Do not symlink or copy `frappe/ui` to work
around it. The official check runs the same step `bench build` runs for this app (`cd hd-frontend && yarn build`), in a
throwaway container from the image, so the running backend and the site volumes are untouched (a build against the live
container writes into its `public/desk/`):

```
cd deploy/docker/compose/nxerp-develop
docker compose run --rm --no-deps -T backend bash -c 'cd apps/helpdesk/hd-frontend && yarn build'
```

It must end with `✓ built in …` and exit 0. It checks the image's current contents, so rebuild the image first
(`deploy/docker/build.sh`) to check working-tree changes; the image build itself also runs this step.

### Empty To on Reply

Send stays enabled while the body has text. With no recipient in To, **Send** and Ctrl+Enter show "Add at least one recipient in
To" inline, send nothing and keep the text; the message clears once a recipient is added. The server enforces the same rule
(`reply_via_email` throws "Add at least one recipient in To").

### Local email testing (Mailpit)

**Dev only. Never use Mailpit on staging or production.** The local develop stack (`deploy/docker/compose/nxerp-develop`) has a
`mailpit` service (`axllent/mailpit`, pinned version) that accepts SMTP on `mailpit:1025` inside the Compose network (not
published) and stores the messages instead of delivering them. Its web UI is `http://localhost:8025` (bound to `127.0.0.1`);
the JSON API is `http://localhost:8025/api/v1/messages`.

To make Reply send locally on a site:

1. Start it: `docker compose up -d mailpit`.
2. Create an outgoing **Email Account** in Desk (or through the API) with Email Address `noreply@nxerp.localhost`, Enable Outgoing
   and Default Outgoing on, SMTP Server `mailpit`, port `1025`, TLS and SSL off, SMTP authentication off (`no_smtp_authentication`),
   Enable Incoming off. Saving runs a live connection test.
3. The scheduler must be enabled for the site (`bench --site <site> scheduler status`; `enable-scheduler` if disabled) and the
   `scheduler` and queue worker services running. After enabling the scheduler, restart the `scheduler` service
   (`docker compose restart scheduler`): a scheduler started while the site was disabled kept skipping it.

A reply is stored as a `Communication`, queued as an Email Queue row, and flushed by the scheduler within about a minute
(status Not Sent, then Sent). Verified on the dev stack: a reply on a task appeared in Mailpit and on the task's Emails tab data,
and a password-reset email for a test user landed there too. This Email Account exists only in that site's database; staging and
production configure their own real outgoing account.

### Task page sidebar (ticket-style)

`TaskSidebar.vue` follows the ticket detail sidebar's format (layout, spacing, type, hover and collapse); the field set is
unchanged. No ticket file is edited: the shared `Section` and `FieldLabel` components and `TicketPriority` are imported as
they are, and everything else lives under `src/pages/tasks/`.

- **Header**: avatar and full name of the creator, `#TASK-xxxx · created <date>` (click copies the id), then two timing rows.
  **Start date**: Not set, Starts in Nd, Starts today, Started <date>. **Due date**: Not set, Due in Nd, Due today (warning
  colour), Overdue by Nd (danger colour); a Completed or Cancelled task shows its plain date. The info icon shows the exact
  date. Clicking a value opens a date picker. "Today" is the server's (`get_task.today`, the site's time zone), not the browser's.
- **Overview** (collapsible): Status, Assignee, Reviewer, Priority, Project, Milestone, each an inline dropdown with a hover
  chevron and a "Set <field>..." placeholder.
  - Status offers only `allowed_statuses`. Blocked and "return from review" open the existing reason dialog on the page, which
    calls `update_status`. The assignee cannot approve their own task (also hidden from managers who are the assignee).
  - Assignee shows avatar, name and a small Employee / Freelancer hint; its dropdown groups Employee (HRMS) and Freelancer
    and saves through `assign_task`. HRMS is asked only when the list opens; if it is down the server's message ("HRMS is
    unavailable") shows inline and freelancers can still be chosen.
  - Reviewer lists the active Agents (`get_task_form_options.employees`). Project lists PBT projects (`pbt:<id>`) and local
    projects, the same sources as the New task dialog. Milestone lists the milestones of the task's local project; a project
    change always empties the milestone in the same save.
  - Priority, Reviewer, Project, Milestone and the dates save through `update_task_fields`.
- **Checklist** (collapsible): `<done> of <total> · <percent>%`, a thin progress bar, checkboxes and an inline add field
  (`update_checklist`; the percentage is the server's).
- **Attachments** (collapsible): a "+" button uploads to the task as before; each file is a chip with a remove button, which
  deletes the File record through Frappe's standard delete after a confirmation (allowed only with write access to the task).
- The collapsed or open state of the three sections is remembered in this browser (`taskSidebarSections`).

The UI only hides options. `HDTask.validate` and the endpoints decide: a stale page, a direct API call or a hand-edited request
gets the same refusal. `test_allowed_statuses_match_what_the_server_accepts` tries every status change for the assignee,
reviewer and a manager and checks that a status is offered exactly when the server accepts it.

### Composer bar (Reply / Comment)

Laid out like the Ticket page's bar (`CommunicationArea`), but task-side only (`TaskActivityComposer.vue`).

- **Closed on load**: opening a task never opens a composer, even when a saved draft exists. Only the bar shows: **Reply** and
  **Comment** on the left with the ticket's icons, and **Cancel** (x icon) at the right end while a composer is open.
- **Reply** / **Comment** open their composer; clicking the open one again closes it. Each composer is created the first time it
  is opened and then only hidden, so switching between them keeps the unsent text and the Reply recipients.
- **Cancel** and **Esc** hide the composer and **keep** the text (the per-task draft in this browser, `taskReply:<task>` and
  `taskActivityComment:<task>`). **Discard** keeps its meaning: it clears the text (and puts the Reply recipients back) and leaves
  the composer open.
- A button shows a small dot while its composer holds an unsent draft, even before it has been opened.
- A successful Send or Comment clears that draft and closes the composer. A failed one keeps the text and shows the error inline
  ("Add at least one recipient in To", "No outgoing email account is configured", ...).

### Gmail-style timestamps (agent ticket page and task page)

Agent ticket and task pages use Gmail-style timestamps (`src/utils/gmailDate.ts`, drawn by `src/components/GmailDate.vue`);
the customer portal keeps relative times ("3 days ago"). Every time on the **Activity**, **Emails** and **Comments** tabs of the
task page and of the agent ticket page uses it, for example
`Wed, Nov 11, 6:30 AM (1 day ago)`. The year is added when it is not the current one: `Mon, Nov 11, 2024, 6:30 AM (2 years ago)`.
Everything else keeps its own format: ticket list columns, the SLA rows, notifications, the Analytics tab and the customer portal.

**How the agent ticket page gets it.** Its email, log and history rows are drawn by the framework's
`ActivityTimeline/TimeAgo.vue` (upstream Frappe code, not edited here), so `hd-frontend/vite.config.js` has a small resolver
(`agentTimelineDates`) that points imports of that one file, made from inside `components/ActivityTimeline/`, at
`components/ticket-agent/timeline/TimelineTimeAgo.vue`, which wraps `GmailDate`. Comment cards (`TimelineCommentRow.vue`)
use the same wrapper directly. Only the agent timeline imports the framework timeline; the portal's conversation
(`TicketConversation` / `TicketCommunication`) does not, so its output is unchanged. The wrapper truncates the longer text with
its tooltip instead of pushing the reply and more icons out of the row.

- **Relative part**: just now (under a minute, and any timestamp slightly ahead of the browser's clock), N minute(s), N hour(s),
  N day(s) (up to 29), N month(s) (at least 1, up to 11), N year(s) ago; singular for 1.
- **Hover**: the full date and time with the zone and offset, e.g. `Wednesday, November 11, 2026, 1:30:12 AM · America/New_York (UTC-05:00)`.
- **Time zone**: server timestamps are naive strings in the system time zone (`window.timezone.system`). They are shown in the logged-in
  user's Frappe time zone (`window.timezone.user`), falling back to the system zone, never the browser's (the browser zone is only a
  last resort when the app has no zone information at all). "Now", the current-year test and the relative part use the same zone.
- **Refresh**: the relative part updates once a minute without a reload, from one shared timer that runs only while a date is on screen.

The frontend has no test runner, so the cases are documented here. They were run on 2026-11-12 by bundling `src/utils/gmailDate.ts` with
esbuild inside the image and stubbing only `@/translation` and the dayjs plugin setup (23 cases, all passed):

| Case | Stored (system zone) | Zones (system → user) | Now | Result |
| --- | --- | --- | --- | --- |
| same year | 2026-11-11 06:30 | UTC → UTC | 2026-11-12 06:30 | `Wed, Nov 11, 6:30 AM (1 day ago)` |
| other year | 2024-11-11 06:30 | UTC → UTC | 2026-11-12 06:30 | `Mon, Nov 11, 2024, 6:30 AM (2 years ago)` |
| afternoon | 2026-11-12 15:05 | UTC → UTC | 15:06 | `Thu, Nov 12, 3:05 PM (1 minute ago)` |
| 1 vs many | 1 / 2 / 59 min, 1 / 5 h, 1 / 3 / 29 d, 1 / 11 months, 1 / 2 years | UTC | | `1 minute ago`, `2 minutes ago`, ..., `1 year ago`, `2 years ago` |
| 30 days | 2026-10-13 09:00 | UTC | 2026-11-12 10:00 | `1 month ago` (never "0 months") |
| just now | 30 s old, or 5 min ahead | UTC | | `just now` |
| zone shift | 2026-11-11 12:00 | Asia/Kolkata → America/New_York | 2026-11-12 06:30 UTC | `Wed, Nov 11, 1:30 AM (1 day ago)` |
| shift across midnight | 2026-11-11 02:00 | Asia/Kolkata → America/New_York | 2026-11-12 06:30 UTC | `Tue, Nov 10, 3:30 PM (1 day ago)` |
| no user zone | 2026-11-11 12:00 | Asia/Kolkata → (none) | 2026-11-12 12:00 IST | `Wed, Nov 11, 12:00 PM (1 day ago)` |
| year boundary | 2025-12-31 23:30 | UTC → Asia/Kolkata | 2026-01-02 00:00 UTC | `Thu, Jan 1, 5:00 AM (1 day ago)` (no year: it is 2026 there) |
