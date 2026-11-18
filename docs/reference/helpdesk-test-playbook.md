# Frappe Helpdesk — Hands-On Test & Mastery Playbook

> **Purpose:** Learn every portal, module and button by *doing*, on your live (or staging) site, with real people playing real roles. Finish with a go/no-go for rolling out to all employees.
> **Companion to:** `HELPDESK_MASTERY_GUIDE.md` (the "what"). This file is the "do it and prove it" version.
> **Built from:** your mastery guide + the actual source code in `helpdesk/` (so button names and behaviours match the app, not just the guide). Your deployed version may differ slightly — anything marked **(verify)** must be confirmed on screen and written down.
> **Note:** No screenshots were found in the workspace. If you share them, this plan can be tightened to your exact UI.

---

## 0. Read This First — Where the Guide Differs From the Real App

Verified against the source. Teach your team the **right-hand column**, not the guide.

| # | Mastery guide says | The app actually does |
|---|---|---|
| 1 | Customer portal at `/my-tickets`, agents at `/helpdesk` | Everything lives under `/helpdesk/…` → customer: `/helpdesk/my-tickets`, agent: `/helpdesk/tickets`. Public KB: `/helpdesk/kb-public` |
| 2 | Settings are pages like `/helpdesk/settings/sla` | **Settings is a pop-up modal** (open from the user menu/sidebar, or `Ctrl/Cmd + ,`). No separate URLs |
| 3 | Roles: Customer / Agent / Admin | Roles are **HD Customer**, **Agent**, **Agent Manager**, **System Manager (= Admin)**. Managers see most settings; **General is Admin-only**; Saved Replies tab is visible to all agents |
| 4 | Statuses: Open, Replied, Waiting on Customer, Resolved, Closed | Default statuses are only **Open, Replied, Resolved, Closed**. Each has a *category*: Open (clock runs), **Paused** (clock stops — `Replied` is Paused by default), Resolved. "Waiting on Customer" does **not** exist unless you create it |
| 5 | Ticket Types, Priorities, Statuses, Templates are Settings tabs | They are **not** in the Settings modal. They are managed in the **Desk** (`/app/hd-ticket-type`, `/app/hd-ticket-priority`, `/app/hd-ticket-status`, `/app/hd-ticket-template`) — needs System Manager (verify exact access on your site) |
| 6 | Reply tabs "Public Reply" / "Internal Note" | Tabs are **Reply** and **Comment** (comment = internal, customer never sees it). Keyboard: `R` = reply, `C` = comment |
| 7 | Home = fixed KPI cards | Home is a **customisable widget dashboard** (buttons: Edit / New / Save / Cancel / Reset / Refresh) |
| 8 | Assignment strategy (Round Robin / Load Balancing) in General settings | Auto-assignment is done by **Settings → Assignment Rules** (Frappe Assignment Rules). General only has "Restrict agent assignment to selected team", "Restrict tickets by team" |
| 9 | CSAT email automatic on resolve; "Require CSAT before closing" | Two separate things: **portal feedback** ("Enable feedback for Customer Portal", on by default) and **email feedback** (`Enabled` + `Send feedback when [status]` — **off by default**). There is no "require before closing" |
| 10 | Auto-close on by default | **Off by default.** When on: closes tickets in a chosen status after N days (default 14) |
| 11 | Availability = Online/Busy/Offline | **Agent Status**: Active / Away / Unavailable (configurable) |
| 12 | Delete / Merge / Split for all agents | **Delete = Admin only.** **Merge** appears only for Open/Paused tickets when >1 ticket exists. **Split** is done from a message in the thread |
| 13 | — (not in guide) | Extras you must also learn: **Command Palette (`Ctrl/Cmd+K`)**, keyboard shortcuts (`Ctrl/Cmd+/`), **Call Logs** + Telephony (Twilio/Exotel), **Field Dependencies**, **Business Holidays**, **Email Notifications** templates, comment **reactions** & pinned comments, **Export**, **Bulk Reply/Assign/Edit**, ERPNext integration, "Allow anyone to create tickets" (guest tickets) |

**Real left-sidebar (agent):** Home · Dashboard · Tickets · Knowledge Base · Customers · Contacts · Call Logs.
**Real Settings modal sections:** *My settings* (Profile, Preferences) · *Email Settings* (Email Accounts, Email Notifications) · *App Settings* (General, Agents, Invite Agents, Teams, SLA Policies, Business Holidays, Assignment Rules, Field Dependencies, Saved Replies) · *Integrations* (Telephony, ERPNext).

---

## 1. Ground Rules for Testing

1. **Use a `[TEST]` prefix** in every subject, customer and article you create so it can be filtered and deleted later.
2. **Test on a staging copy if one exists.** If you test on live: use a dedicated test customer org ("Test Org A/B") and a *test* mailbox; do **not** point real customers at the system until Phase 7.
3. **One person = one role per test.** Use separate browser profiles (or Chrome profile + Incognito + Edge) so you can stay logged in as several people at once.
4. **Write the result next to every test** (Pass / Fail / Different-than-expected + one-line note). The "different" notes are your real training material.
5. Don't use real customer data, real passwords in the log, or real personal emails in screenshots you share.

### 1.1 Test cast (create these first)

| Alias | Role to give | Used for |
|---|---|---|
| **ADMIN-1** | System Manager | Configuration, Desk-only settings, delete |
| **MGR-1** | Agent Manager | Manager-level settings, team dashboards |
| **AGENT-1, AGENT-2, AGENT-3** | Agent (put 1–2 in "Team L1", 3 in "Team L2") | Ticket work, assignment, collaboration |
| **CUST-A1, CUST-A2** | HD Customer, both in **Test Org A** | Same-company visibility test |
| **CUST-B1** | HD Customer in **Test Org B** | Cross-company isolation |
| **MAIL-X** | An outside email address (not a user) | Email-to-ticket and guest tests |

Employees can play agents; for customers use colleagues from another department or personal mailboxes. If you have real friendly customers, add them **only** in Phase 7 pilot.

### 1.2 Result log (copy into Excel/Sheets)

`Test ID | Tester | Role | Date | Pass/Fail/Different | What actually happened | Screenshot? | Action needed`

---

## 2. Suggested Schedule (≈ 5 working days)

| Day | Phases | Who |
|---|---|---|
| 1 | Phase 0 + Phase 1 (admin configuration) | ADMIN-1, MGR-1 |
| 2 | Phase 2 (customer portal) + Phase 3A–3C (agent basics) | Customers + AGENT-1/2 |
| 3 | Phase 3D–3J (advanced agent features) + Phase 4 (KB) | All agents |
| 4 | Phase 5 (end-to-end scenarios, SLA, email) + Phase 6 (permissions/negative) | Everyone together |
| 5 | Phase 7 (dashboard review, pilot, training, go/no-go) | Managers |

---

## PHASE 0 — Environment Sanity (30 min, ADMIN-1)

| ID | Steps | Expected |
|---|---|---|
| 0.1 | Open your domain `https://<your-domain>/helpdesk` | Login page loads over **HTTPS**, no certificate warning |
| 0.2 | Log in as ADMIN-1 | Lands in the agent app; sidebar shows Home, Dashboard, Tickets, Knowledge Base, Customers, Contacts, Call Logs |
| 0.3 | Press `Ctrl/Cmd + /` | Shortcuts modal opens (learn these now — see §3J) |
| 0.4 | Open Settings (`Ctrl/Cmd + ,`) | Modal with My settings / Email Settings / App Settings / Integrations |
| 0.5 | Desk check: open `https://<your-domain>/app` | Desk opens (needed for types/priorities/statuses/templates). Note if access denied |
| 0.6 | Outgoing mail test: Frappe Desk → *Email Account* (or send a password reset to a test user) | Mail arrives. **If no outgoing mail works, stop — nothing in Helpdesk will notify anybody** |
| 0.7 | Check the onboarding/setup screen if one appears (`/helpdesk/onboarding`) | Note what it asks (verify) |

---

## PHASE 1 — Admin Configuration, in This Order (Day 1)

> Order matters: later items depend on earlier ones (e.g. SLA needs holidays/priorities, assignment rules need teams/agents).

### 1A. Profile & Preferences (every user, ADMIN-1 first)
*Settings → My settings → Profile / Preferences*

| ID | Steps | Expected |
|---|---|---|
| 1A.1 | Open Profile; set name, photo | Avatar appears in sidebar/user menu |
| 1A.2 | Open Preferences; explore every option (note what each does) | Changes apply after save (verify per option) |
| 1A.3 | User menu → **Toggle theme** | Light/dark switches |

### 1B. General (Admin only)
*Settings → General.* Test each switch **one at a time**, save, then verify the effect later in Phase 5. Record the *default* value of each before you change it.

| ID | Setting | How to test (quick) | Expected |
|---|---|---|---|
| 1B.1 | Branding (logo, brand name, favicon) | Upload a logo | Shows in sidebar/login/portal |
| 1B.2 | Make feedback mandatory | Toggle on/off | Customer portal ticket shows/hides rating prompt (re-test in 2F) |
| 1B.3 | Enable comment reactions | On | Emoji reaction option appears on comments (3E) |
| 1B.4 | Restrict tickets by team / Do not restrict tickets without a team | On, then log in as AGENT in another team | Agent sees only their team's tickets (+ unassigned-team ones if 2nd box on). **Test in Phase 6** |
| 1B.5 | Restrict agent assignment to selected team | On | Assign dropdown lists only that team's members |
| 1B.6 | Disable global saved replies | On | Global-scope saved replies disappear for agents |
| 1B.7 | Auto update status | On | (verify what flips: observe after customer replies, 5.x) |
| 1B.8 | Allow anyone to create tickets | On | An unregistered person can submit a ticket without account (guest). Test with MAIL-X in 2H. **Security decision — decide deliberately** |
| 1B.9 | Default ticket type | Pick one | New tickets without a type get this one |
| 1B.10 | Automatically close stale tickets | Set status + days = 1 (temporarily) | Resolved tickets older than N days auto-close (check next day). **Reset to a sane value after** |
| 1B.11 | Outside working hours notice | Edit message | Shown to customers outside SLA working hours (verify where) |

### 1C. Desk-managed master data (ADMIN-1 in `/app`)
Create (all prefixed `[TEST]` only if they are throwaway; keep real ones clean):

| ID | Item | Steps | Expected |
|---|---|---|---|
| 1C.1 | **Ticket Types** (`/app/hd-ticket-type`) | Add e.g. *Technical Issue, Billing, Feature Request, Access Request* | Appear in ticket form dropdowns |
| 1C.2 | **Ticket Priorities** (`/app/hd-ticket-priority`) | Confirm Low/Medium/High/Urgent exist; add if needed | Used by SLA table |
| 1C.3 | **Ticket Statuses** (`/app/hd-ticket-status`) | Open the 4 defaults, note *Category*, *Label (Agent)*, *Label (Customer)*. Create **"Waiting on Customer"**, category **Paused**, with customer label "Awaiting your response" | Agent sees "Waiting on Customer"; customer sees the customer label. Paused ⇒ SLA clock stops |
| 1C.4 | **Ticket Templates** (`/app/hd-ticket-template`) | Create "Hardware Request" with extra fields (Device, Serial No., one agent-only field) | Selectable when creating a ticket; agent-only field hidden from customer (verify in 2C) |
| 1C.5 | **Agent Status** (Active/Away/Unavailable) | Review defaults | Appear in agent availability menu |

### 1D. Email Accounts & Notifications
*Settings → Email Settings*

| ID | Steps | Expected |
|---|---|---|
| 1D.1 | **Email Accounts → add** your support mailbox (IMAP in / SMTP out). Use a **test** mailbox first | Connection test passes; account listed |
| 1D.2 | Send an email **from MAIL-X** to the support address; wait for the poll (a few minutes) | A new ticket appears in Tickets list with Source = Email, requester created as a contact |
| 1D.3 | **Email Notifications** → open each template: *Acknowledgement*, *Share Feedback*, *Reply from contact → agent*, *Reply from agent → contact* | Each has editable content + enable switch. Customise acknowledgement, enable it |
| 1D.4 | Send another email → check MAIL-X mailbox | Acknowledgement email arrives (if enabled) |

### 1E. Agents & Teams
| ID | Steps | Expected |
|---|---|---|
| 1E.1 | **Settings → Invite Agents** → invite AGENT-1, 2, 3, MGR-1 (use real mailboxes you control) | Invite emails arrive; they set a password and can log in |
| 1E.2 | **Settings → Agents** | All listed; check how to deactivate/change role (verify) |
| 1E.3 | **Settings → Teams → New Team** "Team L1" (AGENT-1, 2), "Team L2" (AGENT-3) | Teams listed; team page `/helpdesk/teams/<id>` opens |
| 1E.4 | Log in as AGENT-1 in a second browser; open Settings | Agent sees **fewer** sections than Admin (note exactly which) |
| 1E.5 | Log in as MGR-1; open Settings | Sees Email Settings, Agents, Invite, Teams, SLA, Holidays, Assignment Rules, Field Dependencies — but **not General** |

### 1F. Business Holidays & SLA Policies
| ID | Steps | Expected |
|---|---|---|
| 1F.1 | **Business Holidays** → create a holiday list "Test Holidays 2026"; add **today's date + a future date**, plus one recurring holiday. Try calendar and table views | Dates saved and visible |
| 1F.2 | **SLA Policies → New** "[TEST] Org A SLA": condition → customer = Test Org A | Policy saved & enabled |
| 1F.3 | Working days/hours: use a window that covers **now** (e.g. Mon–Sun 00:00–23:59) for testing | Saved |
| 1F.4 | Priority table: set **Urgent: first response 30 min / resolution 2 h** (use short values so breaches are observable; minimum allowed is validated — note it) | Saved, validation messages noted |
| 1F.5 | Attach the holiday list | Linked |
| 1F.6 | Look for the SLA **status/pause** mapping section | Confirm which statuses pause the clock (Paused category) |
| 1F.7 | Create a second SLA "[TEST] Default" marked default | Only one default allowed (validation) |

### 1G. Assignment Rules
| ID | Steps | Expected |
|---|---|---|
| 1G.1 | **Assignment Rules → New**: "[TEST] L1 rotation": Round Robin among AGENT-1, AGENT-2, condition = priority is Low/Medium | Rule saved, enabled |
| 1G.2 | Second rule: "[TEST] Urgent to L2": priority = Urgent → AGENT-3 (or team), higher priority than rule 1 | Saved; priority/order understood |
| 1G.3 | Look at the **Assignment Schedule** part (day/time) | Know how to restrict rules to shifts |
| 1G.4 | Try **Load Balancing** as the rule type (if offered) | Note difference |
| *(verify in 5.2)* | Create tickets and observe who is assigned | Matches rule; first matching/highest-priority wins (confirm exact precedence on screen) |

### 1H. Saved Replies
| ID | Steps | Expected |
|---|---|---|
| 1H.1 | **Saved Replies → New**: "[TEST] Acknowledge" with variables like `{{ doc.contact }}`, `{{ doc.name }}` (check the variable list shown in the editor) | Saved |
| 1H.2 | Make one **Global** and one **Team-scoped** (Team L1 only) | Scope shown |
| 1H.3 | Add a **macro action** if offered (e.g. set status Replied) | Saved |

### 1I. Field Dependencies
| ID | Steps | Expected |
|---|---|---|
| 1I.1 | **Field Dependencies → New**: "if Type = Billing then show/limit field X / value Y" (follow the on-screen criteria/fields/values wizard) | Saved |
| 1I.2 | Test in the ticket form (2C, 3B) | Fields/values react to the chosen type |

### 1J. Integrations (only if you'll use them)
| ID | Steps | Expected |
|---|---|---|
| 1J.1 | **Telephony** (Twilio/Exotel) | Enter credentials in a test account; confirm *Call Logs* page + call buttons on tickets only appear when configured |
| 1J.2 | **ERPNext** integration | Skip unless you run ERPNext; note requirements |

---

## PHASE 2 — Customer Portal (Day 2, play CUST-A1, CUST-A2, CUST-B1)

Create the customer accounts first: add **Test Org A / Test Org B** under *Customers*, add contacts, and invite/create the portal users (HD Customer role) — or let them register if your site allows. Record **exactly how** you created them; that's your onboarding procedure for real customers.

### 2A. Access & routing
| ID | Who | Steps | Expected |
|---|---|---|---|
| 2A.1 | CUST-A1 | Log in at `/helpdesk` | Lands in customer portal (`/helpdesk/my-tickets`), no sidebar of agent modules |
| 2A.2 | CUST-A1 | Manually open `/helpdesk/tickets` and `/helpdesk/dashboard` | Redirected to the customer ticket list; **no** agent data visible |
| 2A.3 | CUST-A1 | Open `/app` | Blocked / no desk access |
| 2A.4 | Anyone | Open `/helpdesk/kb-public` while logged out | Public KB visible (if you have published articles) |

### 2B. Ticket list
| ID | Steps | Expected |
|---|---|---|
| 2B.1 | Check list columns, status badges, search, filters | Statuses show the **customer** label (e.g. "Awaiting Response" for Replied) |
| 2B.2 | Empty state before any ticket | Friendly empty message |

### 2C. Create a ticket (most important customer test)
| ID | Steps | Expected |
|---|---|---|
| 2C.1 | **New ticket** → type subject `[TEST] Invoice export blank page`; watch for KB suggestions while typing | Suggestions appear only if matching published articles exist (create one in Phase 4 and retest) |
| 2C.2 | Try to submit with an empty subject/description | Validation error |
| 2C.3 | Fill type/priority (if shown), rich-text description, bold/list, paste a screenshot, attach a PDF | Everything saved; image previews |
| 2C.4 | Attach a very large file / disallowed type | Clear error; note limits |
| 2C.5 | Submit | Ticket number shown; acknowledgement email arrives (if enabled in 1D) |
| 2C.6 | New ticket via the **Hardware Request template** (`/my-tickets/new` template option) | Template fields shown; **agent-only field NOT visible** |
| 2C.7 | Field dependency from 1I | Behaves as configured |

### 2D. Ticket conversation
| ID | Steps | Expected |
|---|---|---|
| 2D.1 | Open the ticket; check status/priority, thread, attachments | Correct; activity lines visible |
| 2D.2 | Reply with a follow-up | Appears instantly; agent notified; status changes back from Replied → Open (verify) |
| 2D.3 | Agent replies (3C) while the customer page is open | New message appears **without refresh** (real-time) |
| 2D.4 | Look for any **internal comment** text the agent wrote | **Never visible to customer** — critical check |
| 2D.5 | Customer replies by **email** to the notification instead of the portal | Message lands in the same ticket thread |

### 2E. Cross-customer isolation (security-critical)
| ID | Steps | Expected |
|---|---|---|
| 2E.1 | CUST-B1 tries `/helpdesk/my-tickets/<CUST-A1 ticket id>` | Access denied / not found |
| 2E.2 | CUST-A2 (same org as A1) opens A1's ticket | **Record the behaviour.** (Org-wide visibility is a policy question — decide whether it's what you want; HD Customer Manager role/ org membership affects it — verify) |
| 2E.3 | CUST-B1 searches for words from A1's ticket | No results leak |

### 2F. Feedback / rating
| ID | Steps | Expected |
|---|---|---|
| 2F.1 | After agent resolves (5.1), open ticket as customer | Rating prompt on portal ticket (if "Enable feedback for Customer Portal" is on) |
| 2F.2 | Submit 4 stars + comment | Saved; visible to agents on the ticket and in Dashboard feedback widgets |
| 2F.3 | Turn on **email feedback** (1D/General: Enabled + "Send feedback when = Resolved"), resolve another ticket | Email arrives with link `/ticket-feedback/new?key=…`; rating works from the link; reuse of link doesn't double-submit (verify) |

### 2G. Customer-side Knowledge Base
| ID | Steps | Expected |
|---|---|---|
| 2G.1 | Browse categories → open article | Renders formatting/images |
| 2G.2 | 👍/👎 or feedback on an article (verify control) | Recorded; agent sees stats (Phase 4) |
| 2G.3 | Search for text inside an article | Article found |

### 2H. Guest & email-only customers
| ID | Steps | Expected |
|---|---|---|
| 2H.1 | MAIL-X emails support address | Ticket created (1D.2) |
| 2H.2 | With "Allow anyone to create tickets" ON, MAIL-X submits through the public form (verify URL on screen) | Ticket created; with it OFF, blocked |
| 2H.3 | Reply by email from MAIL-X to the agent's reply | Threads into the same ticket |

---

## PHASE 3 — Agent Portal (Days 2–3, play AGENT-1/2/3, MGR-1)

### 3A. Home, notifications, availability
| ID | Steps | Expected |
|---|---|---|
| 3A.1 | Open **Home** → **Edit** → **New** → add several chart widgets → **Save** | Layout persists after reload; **Reset** restores default |
| 3A.2 | Open the **availability/Agent status** menu; set *Away*, then *Unavailable* | Status changes; confirm effect on auto-assignment in 5.2 |
| 3A.3 | Notification bell / `/helpdesk/notifications` | Shows assignments, @mentions, replies; mark as read works |
| 3A.4 | `Ctrl/Cmd+K` command palette | Search tickets, jump to pages, use saved replies, tag actions |

### 3B. Create a ticket as an agent (phone/walk-in case)
| ID | Steps | Expected |
|---|---|---|
| 3B.1 | **Tickets → New**; pick contact (existing) | Customer auto-fills |
| 3B.2 | Create for a **brand-new** contact | Contact is created/linked (verify) |
| 3B.3 | Set priority, type, assignee, team, tags at creation | All saved |
| 3B.4 | Use a **template** | Agent sees agent-only fields too |

### 3C. Ticket list mastery
| ID | Steps | Expected |
|---|---|---|
| 3C.1 | Search by subject, by ticket number, by customer | Works |
| 3C.2 | **Filters**: status, priority, agent, team, type, date, tag; combine 3 | Counts change correctly |
| 3C.3 | **Sort**, **Group by**, **Columns** (add/remove/reorder), **Reset to default** | Persist during session |
| 3C.4 | **Quick filters** (e.g. assigned to me) | Works |
| 3C.5 | **Create View** → name it → reload → switch view | Saved view persists; test **private vs public** if offered |
| 3C.6 | Tick several tickets → **Assign / Reply / Edit / Export** (bulk) | Bulk Assign changes all; Bulk Edit sets a field; Bulk Reply sends individual emails (test with 2 test tickets only); Export downloads a file |
| 3C.7 | `Reload` button | Refreshes list |
| 3C.8 | Tabs/filters for Paused status | "Paused" grouping visible |

### 3D. Ticket detail — every control
Open one ticket; go through each item and note where it is on screen.

| ID | Control | Test | Expected |
|---|---|---|---|
| 3D.1 | Breadcrumb / Prev–Next | `Shift+>` / `Shift+<` | Moves through current list |
| 3D.2 | **Status** dropdown (header) | Open → Replied → Resolved → Closed → reopen | Activity line per change; SLA agreement status updates |
| 3D.3 | **Overview** panel: Assignee, Priority, Type, Team, Tags | Change each; shortcuts `A`,`P`,`T`,`Shift+T`,`G`,`S` | Instant save; activity log; assignee notified |
| 3D.4 | **More details** (template/custom fields) | Edit | Saved |
| 3D.5 | SLA block | Read *response by / resolution by / agreement status* | Matches 1F policy; status Paused when status is Replied |
| 3D.6 | Contact/customer panel | Click contact and organization | Opens profile page |
| 3D.7 | **Recent Tickets** / **Similar Tickets** | Open one | Navigates correctly |
| 3D.8 | Subject edit (pencil/subject modal) | Rename | Saved & logged |
| 3D.9 | `Ctrl/Cmd+.` and `+Shift+.` | Pastes ticket id / URL |
| 3D.10 | Header **⋯ menu**: **Merge Ticket** | Merge ticket B into A (Open tickets only) | B marked merged, conversation moves to A (verify direction) |
| 3D.11 | **Delete** (as Admin vs Agent) | Only Admin sees it | Confirmation dialog; ticket removed |
| 3D.12 | **Split** a customer message into a new ticket | New ticket created from that message; original updated |
| 3D.13 | Custom actions / client scripts (if configured) | Buttons appear |

### 3E. Replying, comments, collaboration
| ID | Steps | Expected |
|---|---|---|
| 3E.1 | Press `R` or click **Reply** → write rich text, attach file → Send | Customer gets an email; thread shows reply; status per settings |
| 3E.2 | Test **CC** and **BCC** with a test address | Delivered correctly |
| 3E.3 | **Comment** tab (`C`): write `@AGENT-2 please check` | Yellow/internal; AGENT-2 notified; **customer cannot see** (verify with CUST account!) |
| 3E.4 | Pin a comment; React to a comment (if enabled in 1B.3) | Pinned bar shows; reactions appear |
| 3E.5 | **Saved Reply** button/selector | Variables substituted with real ticket data; macro action applied |
| 3E.6 | Edit/discard a draft; leave page with unsent text | Draft kept or warned (note which) |
| 3E.7 | Mention someone & check the bell | Notified |
| 3E.8 | Typing indicator (two agents on same ticket) | Shown |
| 3E.9 | Reply on a **mobile** browser | Layout works (MobileTicketAgent) |

### 3F. Customers & Contacts
| ID | Steps | Expected |
|---|---|---|
| 3F.1 | **Customers** list → open Test Org A | Org page with its contacts and tickets |
| 3F.2 | Create/edit/delete org; add contacts | Saved |
| 3F.3 | **Contacts** → open a contact; edit phone/email | Saved; tickets listed |
| 3F.4 | Org-wide SLA assignment (set SLA in org settings if offered) | Linked tickets get that SLA |

### 3G. Call Logs (only if telephony configured)
| ID | Steps | Expected |
|---|---|---|
| 3G.1 | Open Call Logs | List; filters |
| 3G.2 | Click call action on ticket / set contact phone | Call placed; log recorded |

### 3H. My Settings as agent
| ID | Steps | Expected |
|---|---|---|
| 3H.1 | Settings → Saved Replies (agent-created personal reply) | Appears only for them |
| 3H.2 | Preferences | Persist |

### 3I. Team page
| ID | Steps | Expected |
|---|---|---|
| 3I.1 | `/helpdesk/teams/<id>` | Members and team ticket view |

### 3J. Keyboard shortcut drill (10 min — builds speed)
`Ctrl/Cmd+K` palette · `Ctrl/Cmd+,` settings · `Ctrl/Cmd+/` shortcuts · `Ctrl/Cmd+H` help · on a ticket: `R` reply, `C` comment, `A` assign, `S` status, `P` priority, `T` type, `Shift+T` team, `G` tags, `Shift+>/<` next/previous. Every agent must complete one ticket **keyboard-only**.

---

## PHASE 4 — Knowledge Base (Day 3)

| ID | Who | Steps | Expected |
|---|---|---|---|
| 4.1 | AGENT-1 | **Knowledge Base → create category** (and sub-category) | Category visible in tree |
| 4.2 | AGENT-1 | **New Article**: title, rich body with headings, image, code block → **Save as draft** | Draft **not** visible to customers (verify with CUST-A1) |
| 4.3 | AGENT-1 | **Publish** | Visible in portal and `/helpdesk/kb-public` (if public) |
| 4.4 | AGENT-2 | Edit the published article | Changes saved; check version/history behaviour |
| 4.5 | Any agent | Search (KB page + `/helpdesk/search`) | Finds the article by title and body text |
| 4.6 | CUST-A1 | Start a new ticket with a subject matching the article | **Deflection suggestion appears** (re-run 2C.1). Also check the General → "Prefer knowledge base" option |
| 4.7 | CUST-A1 | Give 👍/👎 feedback | Agent sees feedback counts |
| 4.8 | Agent | Insert/link an article in a ticket reply (verify availability) | Link goes to customer |
| 4.9 | Admin | Archive/delete article & empty category | Removed; deleted articles gone from search |

---

## PHASE 5 — End-to-End Scenarios (Day 4, everyone together)

Run each scenario with real people in real roles. Time them.

### Scenario 1 — "The happy path" (Customer → Agent → Resolution → Feedback)
1. CUST-A1 submits `[TEST] Invoice export failing`, priority Urgent.
2. Confirm: ack email, ticket visible to agents, **SLA clock started**, assignment per rule, bell notification to assignee.
3. AGENT-1 sends a Saved Reply (status → Replied). Confirm SLA block shows **Paused**, customer sees "Awaiting Response".
4. CUST-A1 replies → status back to **Open**, clock resumes, agent notified.
5. AGENT-1 adds a Comment @AGENT-3, reassigns to AGENT-3.
6. AGENT-3 replies, sets **Resolved**. Feedback request appears (portal/email per settings).
7. CUST-A1 rates 4★ → rating shows in ticket and Dashboard.
8. Wait for **auto-close** (if enabled) or manually Close.
**Record the full timeline and compare to Mastery Guide §4 Step 9.**

### Scenario 2 — Auto-assignment (1G)
| ID | Steps | Expected |
|---|---|---|
| 5.2a | Create 4 Low tickets in a row (as CUST/agent) | Alternate AGENT-1 / AGENT-2 (Round Robin) |
| 5.2b | Create an Urgent ticket | Goes to AGENT-3 / L2 rule |
| 5.2c | Set AGENT-1 **Unavailable**, create 2 Low tickets | Check whether they skip AGENT-1 (**verify** — availability may not affect rules) |
| 5.2d | Create a ticket matching no rule | Stays unassigned; appears in an "unassigned" filter/view |

### Scenario 3 — SLA behaviour (1F)
| ID | Steps | Expected |
|---|---|---|
| 5.3a | Ticket for Test Org A (matches SLA), do nothing | Response-by countdown shown; after deadline passes **and the hourly scheduler runs**, agreement status → **Failed/breached** (allow up to ~1 hour) |
| 5.3b | Reply in time on another ticket | First-response met → agreement Fulfilled/On track |
| 5.3c | Set status Replied (Paused) for 10 min then back to Open | Deadline extended by paused time |
| 5.3d | Create ticket during a **holiday** date (1F.1) | Deadline skips the holiday |
| 5.3e | Ticket for a non-matching customer | Default SLA applies (or none) |
| 5.3f | Resolve ticket | Resolution time recorded; agreement final state |

### Scenario 4 — Email in/out loop
| ID | Steps | Expected |
|---|---|---|
| 5.4a | MAIL-X emails support (with attachment) | Ticket created, attachment attached |
| 5.4b | Agent replies in Helpdesk | Mail arrives *from the support address*; subject includes ticket ref |
| 5.4c | MAIL-X replies | Same ticket; status Replied → Open |
| 5.4d | MAIL-X sends a brand new email, same subject | New ticket or threads? Note behaviour |
| 5.4e | Auto-reply / out-of-office mail | Does not loop endlessly (note) |
| 5.4f | Agent CC/BCC | Works (3E.2) |

### Scenario 5 — Merge & Split
Duplicate ticket from the same customer → merge; customer sends two issues in one message → split.

### Scenario 6 — Bulk day
Create 10 `[TEST]` tickets → bulk assign to AGENT-1/2 → bulk edit priority → bulk reply (test addresses) → export → verify file.

### Scenario 7 — Shift handover
AGENT-1 sets *Unavailable*, reassigns open tickets with bulk assign; AGENT-2 opens saved view "My open tickets" and continues. Confirm no ticket is orphaned.

---

## PHASE 6 — Permissions & Negative Tests (Day 4)

| ID | Who | Attempt | Expected |
|---|---|---|---|
| 6.1 | AGENT-1 | Open Settings → General | Not visible |
| 6.2 | AGENT-1 | Open `/app/hd-ticket` or other Desk URLs | Denied or limited (note) |
| 6.3 | AGENT-1 | Delete a ticket | Option absent |
| 6.4 | AGENT-3 (Team L2) with "Restrict tickets by team" ON | Open a Team L1 ticket by direct URL | Blocked / filtered |
| 6.5 | MGR-1 | Open Dashboard → **My Organization** vs **My Stats** | Manager sees org/team; agent sees only own (note what agent sees) |
| 6.6 | CUST-A1 | See internal comments, other customers, assignee private info | Never |
| 6.7 | CUST-B1 | Guess ticket IDs `HD-1…N` | Not accessible |
| 6.8 | Deactivate AGENT-2 | They can't log in; their open tickets reassign (verify) |
| 6.9 | Anyone | Wrong password ×5, forgotten password flow | Works / rate-limited |
| 6.10 | Anyone | XSS probe: subject `<b>test</b><script>alert(1)</script>` | Rendered as text, no script runs |
| 6.11 | Anyone | Upload `.exe` or oversize file | Rejected |

---

## PHASE 7 — Analytics, Pilot & Go-Live (Day 5)

### 7A. Dashboard verification (managers)
After Phases 2–5 you have known data. Check the numbers against it:

| ID | Check | Expected |
|---|---|---|
| 7A.1 | Ticket count/volume for today | = number of `[TEST]` tickets you created |
| 7A.2 | Avg first response & resolution time | Plausible vs your timeline |
| 7A.3 | SLA compliance/breach | Includes your 5.3a breach |
| 7A.4 | Feedback widget & Recent feedback | Includes your 4★ rating |
| 7A.5 | Filter by agent, team, date presets (Today / 7 / 30 / 60 / 90 / custom) | Numbers change consistently |
| 7A.6 | Channel/type/priority/tag charts | Reflect test data |
| 7A.7 | Empty states | Show friendly "no data" messages |
| 7A.8 | Ticket Summary **report** (Desk → Report) | Matches dashboard |

### 7B. Clean-up
Filter on `[TEST]` → delete (Admin) or close. Reset temporary settings (auto-close days, short SLA targets, "Allow anyone", shared test accounts' passwords). Deactivate throwaway users.

### 7C. Pilot (1–2 weeks)
- 3–5 real agents + 5–10 friendly customers (one department).
- Daily 15-min stand-up: what confused you? Add to the "Different-than-expected" list.
- Track: tickets/day, avg first response, % with feedback, # of "I couldn't find button X" questions.

### 7D. Go/No-go checklist
- [ ] Outgoing + incoming email proven for a week, no lost mail
- [ ] SLA policies match real business promises (not the short test values)
- [ ] Assignment rules route every ticket type; nothing stays unassigned >1h
- [ ] Roles verified: customers can't see others' data; agents can't reach Admin settings
- [ ] Team restrictions decided (1B.4) and documented
- [ ] Feedback strategy chosen (portal, email or both)
- [ ] 10+ published KB articles for top issues
- [ ] Saved replies for top 10 repetitive responses
- [ ] Backups & upgrade owner named (infra side)
- [ ] One-page quick-start for agents and for customers
- [ ] Support channel for *Helpdesk itself* (who do agents ask?)
- [ ] Data-privacy review done (what customer data enters tickets; retention; who can export) — involve your compliance/legal contact, not just IT

### 7E. Training formats that work
1. **60-min agent workshop:** Phase 3 sections done live (3B–3E + 3J drill).
2. **30-min manager workshop:** Dashboard, SLA, Assignment, views, team restriction.
3. **10-min customer micro-guide:** how to log in, create ticket, reply, rate (screenshots from Phase 2).
4. **Cheat-sheet:** top shortcuts + 5 most common actions.
5. Name 2–3 **champions** (the people who finished all tests) to answer questions in week 1.

---

## Appendix A — Feature Coverage Matrix (tick when tested)

| Module | Tests | Done |
|---|---|---|
| Profile/Preferences | 1A | ☐ |
| General settings (all 11 switches) | 1B, 5, 6 | ☐ |
| Desk master data (types, priorities, statuses, templates) | 1C | ☐ |
| Email accounts & notifications | 1D, 5.4 | ☐ |
| Agents / Invite / Teams | 1E, 3I | ☐ |
| Holidays & SLA | 1F, 5.3 | ☐ |
| Assignment rules | 1G, 5.2 | ☐ |
| Saved replies | 1H, 3E.5 | ☐ |
| Field dependencies | 1I | ☐ |
| Telephony / ERPNext | 1J, 3G | ☐ |
| Customer portal (list, create, thread, feedback) | 2A–2F | ☐ |
| Customer KB / guest tickets | 2G, 2H | ☐ |
| Home widgets / notifications / availability | 3A | ☐ |
| Ticket creation (agent) | 3B | ☐ |
| Ticket list, views, bulk, export | 3C | ☐ |
| Ticket detail, merge, split, delete | 3D | ☐ |
| Reply, comment, mentions, reactions | 3E | ☐ |
| Customers & Contacts | 3F | ☐ |
| Command palette & shortcuts | 3A.4, 3J | ☐ |
| Knowledge base authoring | 4 | ☐ |
| End-to-end scenarios | 5 | ☐ |
| Permissions & security | 6 | ☐ |
| Dashboard & reports | 7A | ☐ |

## Appendix B — Open Questions to Resolve While Testing

Answer these on your live site and add them to the guide: (1) does Agent Status affect auto-assignment? (2) can customers in the same org see each other's tickets? (3) what exactly does "Auto update status" change? (4) what is the minimum SLA target the validator accepts? (5) what happens when an email arrives from a sender with no contact/user? (6) who may open the Desk (`/app`) among agents? (7) is the guest-ticket form reachable and spam-protected? (8) are KB feedback counts visible to agents?
