# 🏆 Frappe Helpdesk — Absolute Mastery Guide
### Every Module · Every Button · Every Feature · Every Flow

> **Purpose:** This guide takes your entire team from zero knowledge to absolute mastery of Frappe Helpdesk — using 3 complete real-world user stories, each broken into step-by-step flows, followed by a full module-by-module reference of every screen and button.

---

## 📋 Table of Contents

1. [Mental Map — How the System is Structured](#1-mental-map)
2. [The Two Portals — What They Are](#2-the-two-portals)
3. [User Flow 1 — Customer Submits a Ticket](#3-user-flow-1--customer-submits-a-ticket)
4. [User Flow 2 — Agent Works a Ticket End-to-End](#4-user-flow-2--agent-works-a-ticket-end-to-end)
5. [User Flow 3 — Admin Configures the Entire System](#5-user-flow-3--admin-sets-up-the-entire-helpdesk)
6. [Module-by-Module Deep Dive (Every Button Explained)](#6-module-by-module-deep-dive)
   - [6.1 Customer Portal — Every Screen](#61-customer-portal--every-screen-and-button)
   - [6.2 Agent Portal — Every Screen](#62-agent-portal--every-screen-and-button)
   - [6.3 Knowledge Base Module](#63-knowledge-base-module)
   - [6.4 Settings Module (Admin Only)](#64-settings-module--admin-only)
   - [6.5 Analytics & Dashboard Module](#65-analytics--dashboard-module)
7. [Key Concepts Glossary](#7-key-concepts-glossary)
8. [Quick Reference — Who Sees What](#8-quick-reference--who-sees-what)

---

## 1. Mental Map

Before diving into flows, build this mental picture:

```
FRAPPE HELPDESK
│
├── 🟦 CUSTOMER PORTAL  (/my-tickets)
│   ├── Submit new ticket
│   ├── Track existing tickets
│   ├── View Knowledge Base articles
│   └── Rate resolved tickets (CSAT)
│
├── 🟩 AGENT PORTAL  (/helpdesk)
│   ├── 🏠 Home Dashboard   → Your personal KPIs & SLA alerts
│   ├── 🎫 Tickets          → Full ticket queue & management
│   ├── 📚 Knowledge Base   → Write and manage help articles
│   ├── 👥 Customers        → Organization profiles
│   ├── 👤 Contacts         → Individual person profiles
│   ├── 📊 Dashboard        → Team analytics & reports
│   └── ⚙️  Settings        → Global system configuration (Admin only)
│
└── 🔴 ADMIN CONTROLS (inside Settings)
    ├── Email Accounts
    ├── SLA Policies
    ├── Teams & Agents
    ├── Ticket Templates
    ├── Saved Replies
    └── Automation / Assignment Rules
```

**Three types of users:**

| User Type | What they access | Key rule |
|-----------|-----------------|----------|
| **Customer** | Customer Portal only | Sees only their own tickets |
| **Agent** | Agent Portal (Tickets, KB, Analytics) | Sees all tickets in their queue |
| **Admin** | Everything including Settings | Full system control |

---

## 2. The Two Portals

### 🟦 Customer Portal
- **URL:** `http://helpdesk.localhost/my-tickets`
- **Who uses it:** End users/customers who need support
- **Design:** Clean, minimal, zero clutter
- **Purpose:** Submit tickets, track progress, browse KB, rate experience

### 🟩 Agent Portal
- **URL:** `http://helpdesk.localhost/helpdesk`
- **Who uses it:** Support agents and managers
- **Design:** Feature-rich, data-dense, productivity-first
- **Purpose:** Work tickets, communicate, monitor SLAs, analyze performance

> **Critical Rule:** A customer who tries to access `/helpdesk/tickets` is automatically redirected to `/my-tickets`. Customers cannot access agent-only views — ever.

---

## 3. User Flow 1 — Customer Submits a Ticket

> **Character:** Priya Sharma (`priya@acmecorp.com`) — customer from Acme Corp
> **Scenario:** Priya's team can't export invoices. The PDF download button is broken.
> **Goal:** Walk through EVERY step Priya takes, every button she sees.

---

### STEP 1 — Priya Opens the Helpdesk URL

**What she sees:** A login page

```
┌───────────────────────────────────┐
│         ACME CORP SUPPORT         │
│                                   │
│  Email:    [priya@acmecorp.com]   │
│  Password: [••••••••••]           │
│                                   │
│           [Log In]                │
│      [Forgot Password?]           │
└───────────────────────────────────┘
```

**What she does:**
1. Enters email and password
2. Clicks **"Log In"**

**Behind the scenes:** System checks her roles (`HD Customer`, `Customer Member`) and redirects her to the Customer Portal.

---

### STEP 2 — Customer Portal Homepage

**URL:** `/my-tickets`

**What she sees:**

```
┌───────────────────────────────────────────────────────────┐
│  🔍 [Search for articles or type your issue...]           │
│                                                           │
│  [+ New Ticket]  (top right)                              │
│                                                           │
│  MY TICKETS                                               │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  #     │ Subject           │ Status   │ Date         │ │
│  │ HD-0041 │ Login issue      │ Closed   │ Oct 10       │ │
│  │ HD-0035 │ Report export    │ Open     │ Oct 8        │ │
│  └──────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

**Every element explained:**

| Element | What it is | What it does |
|---------|-----------|--------------|
| 🔍 **Search Bar** | Global search | Searches Knowledge Base articles AND her own tickets. If she types "invoice export" and a KB article covers it, the article pops up — deflecting the need for a new ticket |
| **+ New Ticket** | Primary action button | Opens the ticket creation form |
| **Ticket list** | Her personal history | All her past tickets with live status |
| **Status badge** | Colored pill | 🟢 Open · 🔵 Replied · 🟡 Waiting · ✅ Resolved · ⚫ Closed |
| **Ticket row** | Clickable | Opens that ticket's full conversation thread |

---

### STEP 3 — Priya Clicks "+ New Ticket"

**What she sees:**

```
┌─────────────────────────────────────────────────────────┐
│               NEW SUPPORT TICKET                         │
│                                                          │
│  Subject *                                               │
│  [Invoice Export Failing — PDF Download Button Broken]   │
│                                                          │
│  ── KB suggestions appear as she types ──                │
│  💡 "How to Export Invoices as PDF"                      │
│  💡 "Invoice Download Troubleshooting Guide"             │
│                                                          │
│  Type *              Priority *                          │
│  [Technical Issue ▼] [High ▼]                           │
│                                                          │
│  Description                                             │
│  [When I click Export PDF on Invoice #INV-0234,          │
│   I get a blank page. This affects the whole team.]      │
│                                                          │
│  Attachments                                             │
│  [📎 Drop files here or click to upload]                 │
│                                                          │
│             [Cancel]   [Submit Ticket]                   │
└─────────────────────────────────────────────────────────┘
```

**Every field explained:**

| Field | Required | What it is |
|-------|----------|------------|
| **Subject** | ✅ Yes | One-line summary. **Smart feature:** As she types, matching KB articles appear below. If she finds her answer there, no ticket needed |
| **KB Suggestions** | Auto | Real-time article suggestions under subject box. Click = opens article. This is called **ticket deflection** |
| **Type** | Depends | Category: Technical Issue / Billing / Feature Request / etc. |
| **Priority** | Depends | Low / Medium / High / Urgent |
| **Description** | ✅ Yes | Full detail. Rich text: bold, bullets, paste screenshots |
| **Attachments** | Optional | Drag-and-drop file upload. Images preview inline |
| **Custom fields** | Varies | If admin configured a custom template (e.g., "Invoice Number", "Affected Month"), these appear here |

**Priya's actions:**
1. Types subject → skims KB suggestions → none solve her exact issue
2. Selects Type: `Technical Issue`, Priority: `High`
3. Types description
4. Uploads a screenshot of the error
5. Clicks **"Submit Ticket"**

---

### STEP 4 — Confirmation

**What she sees:**

```
┌──────────────────────────────────────────────────────────────┐
│  ✅ Ticket Submitted!                                         │
│                                                              │
│  Ticket #HD-0052                                             │
│  "Invoice Export Failing — PDF Download Button Broken"       │
│  Status: Open  |  Expected response: within 4 business hours │
│                                                              │
│                     [View Ticket]                            │
└──────────────────────────────────────────────────────────────┘
```

**Simultaneously in the background (invisible to Priya):**
- Priya gets a **confirmation email:** "We received your ticket #HD-0052"
- Ticket is **auto-assigned** to an agent (Alex) based on assignment rules
- **SLA clock starts** — agent must respond within the configured time

---

### STEP 5 — Priya Views Her Ticket

**URL:** `/my-tickets/HD-0052`

**What she sees:**

```
┌──────────────────────────────────────────────────────────────┐
│  ← Back to Tickets                                           │
│  HD-0052 — Invoice Export Failing...                         │
│  Status: 🟢 Open     Priority: 🔴 High                       │
│                                                              │
│  CONVERSATION                                                │
│  ─────────────────────────────────────────────              │
│  📧 Priya Sharma  (Oct 14, 11:30 AM)                        │
│  "When I click Export PDF on Invoice #INV-0234,              │
│   I get a blank page..."                                     │
│  [📎 screenshot.png]                                         │
│                                                              │
│  ── Ticket created ──                                        │
│  ── Assigned to Agent Alex Chen ──                           │
│                                                              │
│  ─────────────────────────────────────────────              │
│  [  Reply to this ticket...                 ]               │
│  [📎 Attach]                         [Send] │               │
└──────────────────────────────────────────────────────────────┘
```

| Element | What it is |
|---------|------------|
| Status + Priority badges | Live — update automatically when agent acts |
| Conversation thread | Chronological: her messages + agent replies + system events |
| Attachments | Clickable. Images preview inline |
| Activity lines | Grey system events: "Assigned to Alex" — auto-generated |
| Reply box | She can add follow-up messages anytime |
| Send button | Posts follow-up, notifies agent instantly |

---

### STEP 6 — Priya Receives Agent Reply

**Thread updates (real-time if page is open, or via email):**

```
│  💬 Alex Chen — Support Agent  (Oct 14, 12:15 PM)           │
│  "Hi Priya, we've identified the issue — a recent update     │
│   broke the PDF library. Fix in ~2 hours.                    │
│   Workaround: use Export → Excel for now."                   │
│                                                              │
│  ── Status changed: Open → Replied ──                        │
```

---

### STEP 7 — Priya Adds a Follow-Up

1. Clicks the reply box
2. Types her question
3. Clicks **"Send"**
4. Status auto-changes: `Replied → Open` (system detects customer responded)
5. Agent gets notified

---

### STEP 8 — Ticket Resolved + CSAT Email

When agent resolves the ticket, Priya gets an email:

```
Subject: How did we do? Rate your support experience

Your ticket "Invoice Export Failing" has been resolved.

⭐     ⭐⭐    ⭐⭐⭐   ⭐⭐⭐⭐  ⭐⭐⭐⭐⭐
Poor   Fair    OK    Good  Excellent

[Leave a comment...]        [Submit Feedback]
```

**Priya clicks 4 stars → redirected to `/ticket-feedback/new?key=UUID` → submits comment → done.**

Result: CSAT score saved, visible in manager analytics.

---

### 🗺️ Flow 1 Summary

```
Login → Customer Portal → + New Ticket →
(KB deflection check) → Fill form → Submit →
Confirmation email → View Ticket →
Agent replies → Real-time / email update →
Priya adds follow-up → Agent resolves →
CSAT email → Star rating submitted ✅
```

---

---

## 4. User Flow 2 — Agent Works a Ticket End-to-End

> **Character:** Alex Chen (`alex@company.com`) — Support Agent, L1 Team
> **Scenario:** Alex starts his shift, spots Priya's urgent ticket, investigates, collaborates, replies, reassigns, and the ticket is resolved.
> **Goal:** Walk through EVERY step Alex takes in the Agent Portal.

---

### STEP 1 — Alex Logs In → Home Dashboard

**URL:** `/helpdesk`

**Full dashboard layout:**

```
┌──────────────────────────────────────────────────────────────────────┐
│ 🟢 Online ▼              🔔(3)              Alex Chen ▾              │
├───────────────────┬──────────────────────────────────────────────────┤
│ SIDEBAR           │  HOME DASHBOARD                                  │
│                   │                                                  │
│ 🏠 Home           │  ┌────────────┐  ┌────────────┐                 │
│ 🎫 Tickets        │  │ MY TICKETS │  │ SLA ALERTS │                 │
│ 📚 Knowledge Base │  │    12      │  │   🔴 3     │                 │
│ 👥 Customers      │  └────────────┘  └────────────┘                 │
│ 👤 Contacts       │                                                  │
│ 📊 Dashboard      │  AVG FIRST RESPONSE    AVG RESOLUTION            │
│ ⚙️  Settings       │  2h 14m               5h 48m                   │
│                   │                                                  │
│                   │  SLA ALERTS TABLE                                │
│                   │  HD-0052│Priya│🔴 Urgent│Response due: 47m      │
│                   │  HD-0048│John │🟡 High  │Response due: 1h 22m   │
│                   │                                                  │
│                   │  RECENT ACTIVITY                                 │
│                   │  • You replied to HD-0039  (1h ago)             │
│                   │  • You closed HD-0031  (3h ago)                 │
└───────────────────┴──────────────────────────────────────────────────┘
```

**Every element on the Home Dashboard:**

| Element | Location | What it does |
|---------|----------|--------------|
| **🟢 Online ▼** | Top-left | Alex's availability. Click → choose Online / Busy / Offline. If Offline, no tickets auto-assigned to him |
| **🔔 Bell (3)** | Top-right | Unread notification count. Click → dropdown of: new assignments, @mentions, SLA warnings |
| **My Tickets** | Dashboard card | Count of tickets assigned to Alex right now |
| **SLA Alerts** | Dashboard card | Count of tickets at risk of breaching SLA |
| **Avg First Response** | Dashboard metric | Alex's personal average response time |
| **Avg Resolution** | Dashboard metric | Alex's personal average resolution time |
| **SLA Alerts Table** | Main area | Critical tickets with countdown timers. **Red = < 1h. Yellow = 1-4h. Green = safe.** Click any row → opens ticket |
| **Recent Activity** | Main area | Alex's last N actions |
| **Sidebar links** | Left | Navigate between modules |

---

### STEP 2 — Alex Clicks the Notification Bell

```
┌─────────────────────────────────────────┐
│ NOTIFICATIONS                           │
│                                         │
│ 🔴 New ticket assigned to you           │
│    HD-0052 — Invoice Export Failing     │
│    2 minutes ago                        │
│                                         │
│ 🟡 SLA Alert: HD-0048 response due 1h  │
│    15 minutes ago                       │
│                                         │
│ 💬 Raj mentioned you in HD-0039        │
│    1 hour ago                           │
│                                         │
│              [Mark all as seen]         │
└─────────────────────────────────────────┘
```

Alex clicks the first notification → goes to ticket HD-0052.

But first, let's walk through the Tickets List page.

---

### STEP 3 — The Tickets List Page

**URL:** `/helpdesk/tickets`

```
┌────────────────────────────────────────────────────────────────────────┐
│  TICKETS                                          [+ New Ticket]       │
│                                                                        │
│  [🔍 Search tickets...]  [Filters ▼]  [Group By ▼]  [Views ▼]        │
│                                                                        │
│  View: My Open Tickets ▼                                               │
│                                                                        │
│  ☐  │  #    │ SUBJECT                  │ STATUS   │ PRIORITY │ SLA    │
│  ───┼───────┼──────────────────────────┼──────────┼──────────┼────────│
│  ☐  │ 0052  │ Invoice Export Failing   │ 🟢 Open  │ 🔴 Urgent│ 47m   │
│  ☐  │ 0048  │ Login 2FA Not Working    │ 🔵 Replied│ 🟡 High │ 1h 2m │
│  ☐  │ 0044  │ API Rate Limit Error     │ 🟢 Open  │ ⚪ Medium │ 3h   │
│  ☐  │ 0038  │ Report PDF Corrupt       │ 🟢 Open  │ 🟡 High  │ 5h   │
│                                                                        │
│  Showing 4 of 12     [← 1  2  3  →]                                   │
└────────────────────────────────────────────────────────────────────────┘
```

**Every UI element:**

| Element | What it does |
|---------|--------------|
| **+ New Ticket** | Agent creates a ticket on behalf of a customer (for phone/walk-in support) |
| **🔍 Search** | Full-text search across subjects, descriptions, customer names |
| **Filters ▼** | Multi-field filter: Status / Priority / Agent / Team / Type / Customer / Date range / Tag |
| **Group By ▼** | Groups rows by: Status / Priority / Agent / Team / Type |
| **Views ▼** | Switch between saved custom views |
| **View selector** | "My Open Tickets" — click to switch: All Tickets / Unassigned / Urgent / custom views |
| **Column headers** | Click to sort ascending/descending. Drag to reorder |
| **☐ Checkboxes** | Select multiple tickets for bulk actions |
| **SLA column** | Countdown timer. 🔴 < 1h · 🟡 1-4h · 🟢 > 4h |
| **Bulk action bar** | Appears when tickets selected: Assign / Change Status / Priority / Tag / Delete |
| **Pagination** | Navigate pages |

**Saved Views — how they work:**
1. Set filters + sort you want
2. Click **Views ▼ → Save current view**
3. Name it (e.g., "My Urgent Tickets")
4. It appears in the Views dropdown permanently

---

### STEP 4 — Alex Opens Ticket HD-0052 (Full Detail View)

**URL:** `/helpdesk/tickets/HD-0052`

**The split-pane layout:**

```
┌──────────────────────────────────────────────────────────────────────┐
│  ← Tickets   HD-0052                    [Resolve ▼]  [⋮ More]       │
│                         [◀ Prev]  [Next ▶]                           │
├──────────────────────────────┬───────────────────────────────────────┤
│   LEFT PANE                  │   RIGHT PANE                          │
│   CONVERSATION THREAD        │   TICKET METADATA                     │
│                              │                                       │
│  📧 Priya  11:30 AM          │  DETAILS                              │
│  "Invoice Export Failing...  │  Status:   [ Open         ▼ ]        │
│   PDF blank page..."         │  Priority: [ 🔴 Urgent    ▼ ]        │
│  [📎 screenshot.png]        │  Type:     [ Technical    ▼ ]        │
│                              │  Assign:   [ Alex Chen    ▼ ]        │
│  ─ Ticket created ─          │  Team:     [ L1 Support   ▼ ]        │
│  ─ Assigned to Alex Chen ─   │  Tags:     [ + Add tag       ]       │
│                              │                                       │
│                              │  SLA                                  │
│                              │  Response by: 12:17 PM  🔴 47m left  │
│                              │  Resolution:  04:30 PM  🟡 5h left   │
│                              │  Agreement:   ✅ On Track             │
│                              │                                       │
│                              │  CUSTOMER                             │
│                              │  👤 Priya Sharma                      │
│                              │  📧 priya@acmecorp.com                │
│                              │  🏢 Acme Corp                         │
│                              │  Past Tickets: 6  [view all]         │
│                              │                                       │
│  ────────────────────────    │  CUSTOM FIELDS                        │
│  REPLY AREA                  │  Invoice #:  [          ]            │
│                              │  Affected:   [          ]            │
│  [Public Reply][Internal     │                                       │
│   Note] ← tabs               │  CONVERSATION INFO                    │
│                              │  Source: Customer Portal              │
│  [Rich text editor...]       │  Created: Oct 14, 11:30 AM           │
│                              │                                       │
│  CC: [Add...]                │                                       │
│  BCC: [Add...]               │                                       │
│  From: [support@co.com ▼]   │                                       │
│  [📎 Attach] [💬 Saved ▼]   │                                       │
│              [Send Reply →]  │                                       │
└──────────────────────────────┴───────────────────────────────────────┘
```

---

#### LEFT PANE — Every Element Explained

| Element | Background | Visible to customer? | What it is |
|---------|-----------|---------------------|------------|
| **Customer message** | White | ✅ Yes | What the customer wrote |
| **Agent public reply** | Blue/teal | ✅ Yes | Agent's email reply |
| **Internal note** | 🟡 Yellow | ❌ No | Private agent collaboration note |
| **Activity log** | Grey text | ✅ Yes (some) | System events: status changes, assignments |
| **[Public Reply] tab** | — | — | Default. Message sent to customer via email |
| **[Internal Note] tab** | — | — | Switches editor to private mode (yellow border) |
| **Rich text editor** | — | — | Bold, italic, lists, code blocks, @mentions, paste images |
| **@mention** | — | — | Type `@` then agent name → they get notified |
| **CC field** | — | — | Extra email recipients on this reply |
| **BCC field** | — | — | Blind copy recipients |
| **From selector** | — | — | Which support email address sends this reply |
| **📎 Attach** | — | — | Upload file attachment to reply |
| **💬 Saved Reply** | — | — | Opens canned response picker modal |
| **Send Reply →** | — | — | Sends message / email. Thread updates real-time |

#### RIGHT PANE — Every Element Explained

| Section | Element | What it does |
|---------|---------|--------------|
| **Details** | Status ▼ | Change: Open / Replied / Waiting / Resolved / Closed |
| **Details** | Priority ▼ | Change: Low / Medium / High / Urgent |
| **Details** | Type ▼ | Change ticket category |
| **Details** | Assign To ▼ | Search + select any agent |
| **Details** | Team ▼ | Assign to a team |
| **Details** | Tags | Type tag name + Enter. E.g., "pdf-bug", "billing" |
| **SLA** | Response by | Deadline for first reply with countdown |
| **SLA** | Resolution | Deadline for full resolution |
| **SLA** | Agreement status | ✅ On Track / ⚠️ At Risk / ❌ Failed |
| **Customer** | Contact name | Click → opens contact profile page |
| **Customer** | Organization | Click → opens customer org page |
| **Customer** | Past Tickets | Count + "view all" link → full ticket history |
| **Custom Fields** | Template fields | Edit template-specific data for this ticket type |
| **Source** | Info | How ticket was created: Portal / Email / Agent-created / API |

#### HEADER BAR — Every Button

| Button | What it does |
|--------|--------------|
| **← Tickets** | Back to ticket list |
| **[◀ Prev] [Next ▶]** | Navigate to adjacent ticket in current view |
| **[Resolve ▼]** | Dropdown: Quick-resolve, quick-close, or other status jump |
| **[⋮ More]** | Extra actions: Merge ticket / Split ticket / Delete ticket / View history |

---

### STEP 5 — Alex Leaves an Internal Note

Alex needs to loop in senior engineer Raj — privately:

1. Clicks **"Internal Note"** tab (editor border turns yellow)
2. Types: `@Raj — Can you check if the PDF fix from PR #234 is deployed? Customer is Enterprise.`
3. Clicks **"Send Reply"**

**Result:**
- Yellow note appears in thread — **customer CANNOT see this**
- Raj gets notification: "Alex mentioned you in HD-0052"
- Raj opens the ticket, sees the internal note, responds in another internal note

---

### STEP 6 — Alex Uses a Saved Reply

Instead of writing the workaround from scratch:

1. In **Public Reply** tab, clicks **💬 Saved Reply**
2. **Modal opens:**

```
┌────────────────────────────────────────────────┐
│  🔍 Search saved replies...                     │
│                                                 │
│  📝 PDF Export Workaround                       │
│     "Hi {{contact}}, we found a workaround..."  │
│                                                 │
│  📝 Escalation Acknowledgement                  │
│     "Your ticket has been escalated to..."      │
│                                                 │
│  📝 Closing — Issue Resolved                    │
│     "We're glad to confirm the issue is..."     │
└────────────────────────────────────────────────┘
```

3. Clicks **"PDF Export Workaround"**
4. Text fills into editor with **variables already substituted:**
   - `{{doc.contact}}` → "Priya"
   - `{{doc.customer}}` → "Acme Corp"
5. Alex tweaks it slightly → clicks **Send Reply**

**Priya receives the email reply within seconds.**

---

### STEP 7 — Alex Changes Status & Reassigns

The fix is going to be handled by Raj:

1. Alex clicks **Assign To ▼** → searches "Raj" → selects "Raj Kumar"
2. Raj gets notification: "Ticket HD-0052 assigned to you"
3. Alex changes **Status ▼** → "Waiting on Customer"

**Critical effect:** Changing to "Waiting on Customer" **pauses the SLA clock.** The countdown stops. Ticket moves out of Alex's urgent queue.

---

### STEP 8 — Raj Resolves the Ticket

After deploying the fix, Raj:
1. Writes final reply to Priya
2. Clicks **[Resolve ▼]** at the top right

```
┌──────────────────────────────────────┐
│  Resolve Ticket                      │
│                                      │
│  Status will change to: Resolved     │
│                                      │
│  Send CSAT feedback email?           │
│  ☑ Yes — send rating request         │
│                                      │
│        [Cancel]  [Confirm Resolve]   │
└──────────────────────────────────────┘
```

3. Confirms → CSAT email sent to Priya automatically

---

### STEP 9 — The Full Ticket Timeline

After all activity, the conversation shows:

```
11:30 AM  📧 Priya — "Invoice export failing..."
11:32 AM  ── Ticket created ──
11:32 AM  ── Assigned to Alex Chen ──
11:35 AM  🟡 Alex (Internal) — "@Raj check PR #234..."
11:40 AM  💬 Alex — "Hi Priya, workaround: use Export Excel..."
11:40 AM  ── Status changed: Open → Replied ──
12:05 PM  📧 Priya — "Workaround works! When is real fix?"
12:05 PM  ── Status changed: Replied → Open ──
12:10 PM  ── Assigned to Raj Kumar ──
12:10 PM  ── Status changed: Open → Waiting on Customer ──
02:30 PM  💬 Raj — "Fix deployed! Please confirm."
03:00 PM  📧 Priya — "Confirmed, working now. Thank you!"
03:05 PM  ── Status: Waiting → Resolved ──
03:05 PM  ── CSAT email sent ──
```

---

### STEP 10 — Agent Creates a Ticket on Behalf of a Customer

A customer called by phone. Alex creates a ticket for them:

1. Clicks **+ New Ticket** on the Tickets list page
2. Form opens — same as customer form but with EXTRA agent-only fields:
   - **Contact** field (search existing contacts)
   - **Customer** (auto-fills from contact)
   - **Assign To** (can assign immediately)
   - **Team** (can route immediately)
3. Fills details → **Submit**

---

### 🗺️ Flow 2 Summary

```
Login → Home Dashboard → Notification Bell →
Tickets List (filters, bulk actions, saved views) →
Open Ticket (split pane: conversation + metadata) →
Internal Note @mention colleague →
Saved Reply with Jinja variables →
Status change → Reassign → SLA pauses →
Resolution → CSAT trigger →
Full timeline visible ✅
```

---

---

## 5. User Flow 3 — Admin Sets Up the Entire Helpdesk

> **Character:** Meera Nair (`meera@company.com`) — IT Admin / Manager
> **Scenario:** Company just deployed Frappe Helpdesk. Meera configures everything from scratch.
> **Goal:** Walk through EVERY Settings module.

---

### STEP 1 — First-Time Onboarding Checklist

When Meera first logs in as Admin:

```
┌──────────────────────────────────────────────────────────────┐
│  🎉 Welcome to Frappe Helpdesk!                              │
│                                                              │
│  Complete these steps to get started:                        │
│                                                              │
│  ✅  1. Connect Email Account        [Done ✓]               │
│  ☐   2. Invite your first agent      [Set Up →]             │
│  ☐   3. Create your first SLA        [Set Up →]             │
│  ☐   4. Customize ticket form        [Set Up →]             │
│  ☐   5. Add a Knowledge Base article [Set Up →]             │
│                                                              │
│  Progress: ██░░░░░░░░  20%                                   │
└──────────────────────────────────────────────────────────────┘
```

Each step links directly to the relevant settings section.

---

### STEP 2 — Settings Navigation

**URL:** `/helpdesk/settings`

```
⚙️ SETTINGS
├── General
├── Email Accounts
├── Agents
├── Teams
├── SLA Policies
├── Ticket Types
├── Ticket Priorities
├── Ticket Statuses
├── Ticket Templates
├── Saved Replies
├── Knowledge Base
└── Branding / Portal
```

---

### STEP 3 — General Settings

**URL:** `/helpdesk/settings/general`

| Setting | What it controls |
|---------|-----------------|
| **Allow customer portal?** | Whether customers can access the self-service portal |
| **Default ticket template** | Which form template new tickets use |
| **Auto-close after N days** | Resolved tickets auto-close after this many days |
| **Send CSAT email on resolve** | Auto-email rating link when ticket is resolved |
| **Require CSAT before closing** | Agent can't close ticket until customer rates |
| **Enable auto-assignment** | Auto-assign new tickets to agents/teams |
| **Round Robin vs Load Balancing** | Round Robin = cyclic turns · Load Balancing = least busy agent |

---

### STEP 4 — Email Accounts Setup

**URL:** `/helpdesk/settings/email-accounts`

This connects your support email inbox.

```
ADD EMAIL ACCOUNT

  Email Address: [support@acmecorp.com]
  Display Name:  [Acme Corp Support]

  ── Incoming (IMAP) ──
  IMAP Server:  [imap.gmail.com]
  Port:         [993]
  Use SSL:      ☑ Yes
  App Password: [•••••••••••••••]

  ── Outgoing (SMTP) ──
  SMTP Server:  [smtp.gmail.com]
  Port:         [587]
  Use TLS:      ☑ Yes

  [Test Connection]       [Save]
```

**What this does:**
- **IMAP (Incoming):** Helpdesk polls inbox. Customer emails `support@acmecorp.com` → ticket created automatically
- **SMTP (Outgoing):** Agent replies send FROM this address
- **Email threading:** `Message-ID` / `In-Reply-To` headers tracked — all replies stay in same ticket thread

---

### STEP 5 — Inviting Agents

**URL:** `/helpdesk/settings/agents`

1. Click **+ Invite Agent**
2. Enter email, select team
3. Click **Send Invitation**
4. Agent receives link → sets password → linked to `HD Agent` record

**Agent settings configurable:**
- Availability (Online / Busy / Offline)
- Team membership
- Active / Inactive (inactive = excluded from auto-assignment)

---

### STEP 6 — Creating Teams

**URL:** `/helpdesk/settings/teams`

```
Team Name:    [L2 Engineering]
Description:  [Handles escalated tech issues]
Members:      [Alex ×]  [Raj ×]  [+ Add]
```

Teams used for:
- **Routing:** "Technical Issue" tickets → L2 Engineering team
- **Saved replies scoping:** Some replies visible only to Billing team
- **Analytics:** Filter dashboard metrics by team

---

### STEP 7 — Configuring SLA Policies

**URL:** `/helpdesk/settings/sla`

```
NEW SLA POLICY

  Name: [Enterprise SLA]
  Active: ☑

  ── Conditions (when does this SLA apply?) ──
  Customer:  [Acme Corp ▼]
  Priority:  [Urgent ▼]
  (Or: custom condition: doc.customer == 'Acme Corp')

  ── Response & Resolution Targets ──
  Priority │ First Response │ Resolution
  Urgent   │ 1 hour         │ 4 hours
  High     │ 4 hours        │ 8 hours
  Medium   │ 8 hours        │ 24 hours
  Low      │ 24 hours       │ 72 hours

  ── Working Hours ──
  Monday:   09:00 → 18:00  ☑
  Tuesday:  09:00 → 18:00  ☑
  Saturday: —              ☐ (off)
  Sunday:   —              ☐ (off)

  ── Holiday List ──
  [India Holidays 2026 ▼]
  (SLA clock pauses on these dates)

                              [Save SLA Policy]
```

**How SLA works once configured:**
1. Ticket created → system evaluates ALL active SLAs in order
2. First SLA whose conditions match → applied to ticket
3. Deadlines computed respecting working hours + holidays
4. Status → "Waiting on Customer" → **SLA clock pauses**
5. Customer replies → **SLA clock resumes** (deadline extends by paused duration)
6. Hourly scheduler checks deadlines → breached → `agreement_status = "Failed"` → SLA Alerts

---

### STEP 8 — Ticket Templates

**URL:** `/helpdesk/settings/ticket-templates`

```
NEW TICKET TEMPLATE: Hardware Replacement Request

FIELDS:
  Label          │ Type   │ Required │ Visible To
  Subject        │ Text   │ ✅ Yes   │ Everyone
  Description    │ Text   │ ✅ Yes   │ Everyone
  Device Type    │ Select │ ✅ Yes   │ Everyone
  Serial Number  │ Text   │ ✅ Yes   │ Everyone
  Purchase Date  │ Date   │ ☐ No    │ Everyone
  Internal Notes │ Text   │ ☐ No    │ Agents Only ← customer never sees this
```

| Setting | Effect |
|---------|--------|
| **Required = Yes** | User cannot submit without filling |
| **Visible To: Everyone** | Shown to both customers and agents |
| **Visible To: Agents Only** | Hidden from customer portal form — customer can't see or set it |

---

### STEP 9 — Saved Replies

**URL:** `/helpdesk/settings/saved-replies`

```
NEW SAVED REPLY

  Title: [PDF Export Workaround]
  Team:  [L1 Support ▼]  (blank = all teams)

  Message:
  ┌────────────────────────────────────────────────────────┐
  │ Hi {{ doc.contact }},                                  │
  │                                                        │
  │ We found a workaround for the PDF export issue:        │
  │ 1. Go to Reports > Invoices                            │
  │ 2. Use "Export Excel" instead of "Export PDF"          │
  │                                                        │
  │ Full fix expected within 2 hours.                      │
  │                                                        │
  │ Best,                                                  │
  │ {{ frappe.session.user }}                               │
  └────────────────────────────────────────────────────────┘

  MACRO ACTIONS (when reply is sent, also):
  ☑ Change status to: [Replied ▼]
  ☐ Change priority to: [–]
  ☐ Assign to: [–]

                                     [Save Reply]
```

**Jinja variables available:**
- `{{ doc.contact }}` → Contact's name
- `{{ doc.customer }}` → Customer/company name
- `{{ doc.subject }}` → Ticket subject
- `{{ doc.name }}` → Ticket number (HD-0052)
- `{{ frappe.session.user }}` → Agent's name

**Macro actions:** Sending this reply ALSO automatically changes status/priority/assignment. Powerful for standardizing workflows.

---

### STEP 10 — Knowledge Base Setup

**Creating a Category:**
1. Click **+ New Category**
2. Name: "Invoice & Billing"
3. Set parent (hierarchical) or leave as root
4. Visibility: Public / Customers Only / Agents Only

**Creating an Article:**
```
Title:    [How to Export Invoices as PDF]
Category: [Invoice & Billing ▼]

[Rich text editor — write the guide with headers, steps, screenshots]

Status: ● Published  ○ Draft

              [Save Draft]   [Publish Article]
```

**Once published:**
- Visible in customer KB portal
- Indexed in SQLite full-text search engine
- Appears as ticket deflection suggestions on New Ticket form

---

### STEP 11 — Assignment Rules

**URL:** `/helpdesk/settings/assignment-rules`

```
NEW ASSIGNMENT RULE

  Name: [Route Urgent Technical to L2 Engineering]

  Conditions (ALL must be true):
  ticket_type  equals  Technical Issue
  priority     equals  Urgent

  Assign To Team: [L2 Engineering ▼]
  Strategy: ● Round Robin  ○ Load Balancing

                                    [Save Rule]
```

Multiple rules evaluated in priority order. First match wins.

---

### 🗺️ Flow 3 Summary

```
Onboarding checklist →
General Settings (portal, auto-close, CSAT, assignment strategy) →
Email Account (IMAP/SMTP connect + test) →
Invite Agents (send invitation emails) →
Create Teams (group agents by function) →
SLA Policies (response targets + working hours + holidays) →
Ticket Templates (custom fields per use case) →
Saved Replies (canned responses + macro actions) →
Knowledge Base (categories + published articles) →
Assignment Rules (auto-routing logic) ✅
```

---

---

## 6. Module-by-Module Deep Dive

### 6.1 Customer Portal — Every Screen and Button

#### `/my-tickets` — Ticket List

| Element | What it does |
|---------|--------------|
| **+ New Ticket** | Opens ticket creation form |
| **Search bar** | Searches KB + their own tickets |
| Ticket list rows | Click any row → opens that ticket |
| Status filter tabs | Filter: All / Open / Resolved / Closed |
| Status badge | 🟢 Open · 🔵 Replied · 🟡 Waiting · ✅ Resolved · ⚫ Closed |

#### `/my-tickets/new` — New Ticket Form

| Element | What it does |
|---------|--------------|
| Subject | One-line description. Triggers KB deflection suggestions |
| KB suggestions | Click → opens article. Deflects ticket creation |
| Ticket Type | Category dropdown |
| Priority | Urgency dropdown (if visible) |
| Description | Rich text editor |
| Attachments | Drag-drop / browse |
| Custom fields | Template-specific extra fields |
| **Cancel** | Back without creating |
| **Submit Ticket** | Creates ticket + sends confirmation email |

#### `/my-tickets/HD-XXXX` — Ticket Detail

| Element | What it does |
|---------|--------------|
| Status/Priority badges | Live, updates in real time |
| Conversation thread | Messages in chronological order |
| Agent replies | What the support team sent |
| Activity entries | System events (grey text) |
| Reply box | Customer adds follow-ups |
| **Send** | Posts reply, notifies agent, reopens ticket |

#### `/ticket-feedback/new?key=UUID` — CSAT Rating

| Element | What it does |
|---------|--------------|
| Star rating (1-5) | Click to select satisfaction level |
| Feedback text box | Optional comment |
| **Submit Feedback** | Saves to system, visible in analytics |

---

### 6.2 Agent Portal — Every Screen and Button

#### `/helpdesk` — Home Dashboard

| Element | Location | What it does |
|---------|----------|--------------|
| **Availability toggle** | Top-left | Online/Busy/Offline — controls auto-assignment |
| **🔔 Bell** | Top-right | Unread count · click → notification list |
| **User menu ▾** | Top-right | Profile / Logout |
| My Tickets card | Dashboard | Count of my assigned open tickets |
| SLA Alerts card | Dashboard | Count of tickets near breach |
| Avg First Response | Dashboard | My personal metric |
| Avg Resolution | Dashboard | My personal metric |
| SLA Alerts Table | Dashboard | Urgent tickets with countdowns. Click → ticket |
| Recent Activity | Dashboard | My last N actions |
| Sidebar | Left | Module navigation |

#### `/helpdesk/tickets` — Ticket List

| Element | What it does |
|---------|--------------|
| **+ New Ticket** | Create ticket for customer (agent-side) |
| **Search** | Full-text search |
| **Filters ▼** | Status / Priority / Agent / Team / Type / Customer / Date / Tag |
| **Group By ▼** | Group by any field |
| **Views ▼** | Saved filter views |
| Column headers | Click to sort, drag to reorder |
| **☐ Checkboxes** | Multi-select for bulk actions |
| **Bulk actions bar** | Assign / Status / Priority / Tag / Delete |
| SLA column | Colored countdown |
| Pagination | Navigate pages |

#### `/helpdesk/tickets/HD-XXXX` — Ticket Detail

**Header:**

| Button | What it does |
|--------|--------------|
| ← Tickets | Back to list |
| ◀ Prev / Next ▶ | Navigate tickets |
| **Resolve ▼** | Quick status actions |
| **⋮ More** | Merge / Split / Delete / History |

**Left Pane:**

| Element | What it does |
|---------|--------------|
| Customer messages | White bg — public |
| Agent replies | Blue bg — public, sent via email |
| Internal notes | 🟡 Yellow bg — agents only |
| Activity logs | Grey — system events |
| **Public Reply tab** | Default reply mode |
| **Internal Note tab** | Private note mode (editor turns yellow) |
| Rich text editor | Full formatting + @mentions |
| CC / BCC | Extra email recipients |
| From selector | Which support email sends |
| 📎 Attach | Upload to reply |
| 💬 Saved Reply | Canned response picker |
| **Send Reply** | Sends + updates thread |

**Right Pane:**

| Element | What it does |
|---------|--------------|
| Status ▼ | Change status |
| Priority ▼ | Change priority |
| Type ▼ | Change category |
| Assign To ▼ | Assign agent |
| Team ▼ | Assign team |
| Tags | Add labels |
| SLA: Response by | Deadline + countdown |
| SLA: Resolution | Deadline + countdown |
| Agreement status | ✅ On Track / ⚠️ At Risk / ❌ Failed |
| Customer info | Click name/org → opens profile |
| Past Tickets count | History + link |
| Custom fields | Template-specific editable fields |

---

### 6.3 Knowledge Base Module

**Agent-side (authoring):**

| Element | What it does |
|---------|--------------|
| Category tree | Browse topic hierarchy |
| **+ New Category** | Create topic group |
| **+ New Article** | Open article editor |
| Rich text editor | Markdown + WYSIWYG |
| **Save as Draft** | Not visible to customers yet |
| **Publish** | Makes article live |
| Article list | Shows all articles, status, views, feedback score |

**Customer-side (reading):**

| Element | What it does |
|---------|--------------|
| Category cards | Browse topics visually |
| Search bar | Full-text search (SQLite FTS powered) |
| Article page | Rendered article with formatting |
| 👍 / 👎 | Vote on helpfulness |
| Related articles | Auto-suggested |

---

### 6.4 Settings Module (Admin Only)

| Section | Key Controls |
|---------|-------------|
| **General** | Portal toggle, auto-close days, CSAT settings, assignment strategy |
| **Email Accounts** | Add/edit IMAP+SMTP, test connection |
| **Agents** | Invite, set team, active/inactive |
| **Teams** | Create, add members |
| **SLA** | Policies, targets per priority, working hours, holidays |
| **Ticket Types** | Bug / Feature Request / Billing / etc. |
| **Ticket Priorities** | Low / Medium / High / Urgent — colors |
| **Ticket Statuses** | Open / Replied / Waiting / Resolved / Closed — categories |
| **Ticket Templates** | Custom fields per request type |
| **Saved Replies** | Canned responses + Jinja variables + macro actions |
| **Assignment Rules** | Auto-routing conditions |
| **Knowledge Base** | Visibility, homepage customization |
| **Branding** | Logo, colors, custom domain |

---

### 6.5 Analytics & Dashboard Module

**URL:** `/helpdesk/dashboard`

| Widget | What it shows |
|--------|--------------|
| Ticket Volume chart | Tickets over time (daily/weekly/monthly) |
| SLA Compliance % | What % of tickets met SLA targets |
| Avg First Response | From creation → first reply |
| Avg Resolution Time | From creation → resolution |
| CSAT Score | Average customer rating |
| Filter by Agent | Per-agent metrics |
| Filter by Team | Per-team metrics |
| Filter by Priority | Metrics by urgency level |
| Date Range picker | Any custom date window |
| SLA Breach breakdown | Which tickets failed + by how much |

---

## 7. Key Concepts Glossary

| Term | Plain English |
|------|--------------|
| **Ticket** | A support case file. Everything about one customer issue lives here |
| **Status** | Where the ticket is in the workflow: Open → Replied → Waiting → Resolved → Closed |
| **Status Category** | Groups: **Open** (clock running) · **Paused** (waiting, clock stopped) · **Resolved** (done) |
| **Priority** | Urgency: Low < Medium < High < Urgent |
| **SLA** | Service Level Agreement — a promise about how fast you'll respond/resolve |
| **First Response** | The very first agent reply to the customer |
| **Resolution** | When problem is fully fixed and ticket is marked Resolved |
| **CSAT** | Customer Satisfaction score — rating customer gives after resolution |
| **Internal Note** | Agent-only message. Invisible to customer. Used for team collaboration on a ticket |
| **Saved Reply** | Pre-written template with Jinja variables. Agents insert to reply faster |
| **Ticket Template** | Custom form layout defining which fields appear on the New Ticket form |
| **Assignment Rule** | Auto-rule: "Technical Issue tickets → assign to L2 Engineering team" |
| **Round Robin** | Assignment: Ticket 1→Agent A, Ticket 2→Agent B, Ticket 3→Agent A... (cyclic) |
| **Load Balancing** | Assignment: Always assign to agent with fewest open tickets |
| **SLA Breach** | Deadline was missed — ticket flagged "Failed", appears in SLA Alerts in red |
| **Ticket Deflection** | Customer finds KB article and self-resolves instead of creating a ticket |
| **Knowledge Base** | Library of help articles. Customers browse to self-serve |
| **Contact** | An individual person (a user at the customer's company) |
| **Customer** | An organization/company that receives support |
| **Working Hours** | Defined business schedule. SLA clock ticks ONLY during these hours |
| **Holiday List** | Calendar of dates when SLA clock is paused entirely |
| **Real-time updates** | Page updates automatically (new ticket appears, status changes) without refreshing — powered by WebSockets |

---

## 8. Quick Reference — Who Sees What

| Feature | Customer | Agent | Admin |
|---------|----------|-------|-------|
| Submit new ticket | ✅ | ✅ | ✅ |
| View own tickets | ✅ | ❌ (sees all) | ✅ |
| View ALL tickets | ❌ | ✅ | ✅ |
| See internal notes | ❌ | ✅ | ✅ |
| Reply to ticket | ✅ | ✅ | ✅ |
| Change status | ❌ | ✅ | ✅ |
| Change priority | ❌ | ✅ | ✅ |
| Assign ticket | ❌ | ✅ | ✅ |
| Use saved replies | ❌ | ✅ | ✅ |
| Write internal notes | ❌ | ✅ | ✅ |
| Browse knowledge base | ✅ | ✅ | ✅ |
| Write KB articles | ❌ | ✅ | ✅ |
| View analytics dashboard | ❌ | ✅ | ✅ |
| Access Settings | ❌ | ❌ | ✅ |
| Configure SLA | ❌ | ❌ | ✅ |
| Invite agents | ❌ | ❌ | ✅ |
| Configure email | ❌ | ❌ | ✅ |
| Create ticket templates | ❌ | ❌ | ✅ |
| Create saved replies | ❌ | ❌ | ✅ |
| Set assignment rules | ❌ | ❌ | ✅ |
| Rate ticket (CSAT) | ✅ | ❌ | ❌ |
| Toggle availability | ❌ | ✅ | ✅ |
| Bulk actions on tickets | ❌ | ✅ | ✅ |
| Merge / Split tickets | ❌ | ✅ | ✅ |

---

> **📌 Recommended Team Practice:**
> 1. Walk through **Flow 1** as a customer — submit a real test ticket on your live system
> 2. Walk through **Flow 2** as an agent — respond to that same test ticket end-to-end
> 3. Walk through **Flow 3** as admin — configure each settings section one by one
>
> Doing this hands-on in sequence will give your team faster, deeper mastery than any amount of reading.

---

*For the technical/code-level architecture, see `FRAPPE_HELPDESK_KNOWLEDGE_MAP.md` and `FRAPPE_HELPDESK_PIPELINE.md` in your workspace.*
