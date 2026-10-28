# 📘 Frappe Helpdesk — Complete System Pipeline
### Every File Explained | Data Flow from Browser Click to Database and Back

> **Your starting assumption**: You know nothing about Frappe, Django, Vue, or how web servers work internally.
> This guide explains what **every single file does**, what **format the data travels in** at each step, and **why** it was built that way.

---

## 🗺️ Before We Start: What Is Frappe?

Think of **Frappe** like Django (a Python web server) but with super-powers:
- It has a built-in **database ORM** (you don't write raw SQL, it writes it for you).
- It has a built-in **permission system** (it automatically enforces who can read/write what).
- It has **"DocTypes"** — which are like database table definitions that also carry business logic.
- It auto-generates REST API endpoints for every DocType.

**Frappe Helpdesk** is an *app* that runs *on top of* Frappe. It adds the ticket management features.

---

## 🎬 The Scenario We're Following

> **Sarah** (`sarah@acme.com`), a customer from *Acme Corp*, is logged into the **Customer Portal** in her browser.
> She submits an urgent support ticket: **"Production Payment Gateway 502 Error"**.
>
> Meanwhile, **Alex** (a support agent) has the **Agent Dashboard** open in another browser tab.
>
> We will watch **exactly** what code runs, in what order, and in what file, from the moment Sarah clicks "Submit" until Alex sees the new ticket appear on his screen — without refreshing.

---

## 🧭 The Master Pipeline Diagram

```mermaid
flowchart TD

  %% ─────────────────────────────────────────────────────
  subgraph BROWSER_SARAH ["🌐 STEP 1 — Sarah's Browser"]
    direction TB
    s1a["index.html loads the Vue app"]
    s1b["desk/src/main.js\n─────────────────\nBootstraps Vue, registers Pinia,\nrouter, frappe-ui, Socket.IO client"]
    s1c["desk/src/App.vue\n─────────────────\nRoot component. Renders the active page."]
    s1d["desk/src/router/index.ts\n─────────────────\nReads the URL path.\nDecides which page component to show.\nBlocks non-agents from /tickets."]
    s1e["desk/src/roots/PortalRoot.vue\n─────────────────\nChecks authStore.isAgent.\nLoads AgentRoot or CustomerPortalRoot shell."]
    s1f["desk/src/roots/CustomerPortalRoot.vue\n─────────────────\nCustomer UI wrapper:\nNavbar, sidebar, ticket list link."]
    s1g["desk/src/pages/ticket/TicketNew.vue\n─────────────────\nThe 'New Ticket' form page.\nBinds inputs with v-model.\nOn submit → calls frappe-ui createResource()"]
    s1h["desk/src/stores/auth.ts ← useAuthStore\n─────────────────\nHolds: who is logged in, roles,\nisAgent, hasDeskAccess, availability.\nPulled from helpdesk.api.auth.get_user"]

    s1a --> s1b --> s1c --> s1d --> s1e --> s1f --> s1g
    s1h -.feeds role info.-> s1e
  end

  %% ─────────────────────────────────────────────────────
  subgraph HTTP_LAYER ["📡 STEP 2 — HTTP Request is Built & Sent"]
    direction TB
    h1["frappe-ui: createResource()\n─────────────────\nA wrapper around fetch().\nSerializes the form data to JSON.\nAttaches the session cookie 'sid=...'"]
    h2["JSON Payload over HTTP POST\n─────────────────\nPOST /api/method/helpdesk.api.doc.create_doc\nContent-Type: application/json\nCookie: sid=abc123\n\n{ doctype: 'HD Ticket',\n  subject: '502 Error...',\n  priority: 'Urgent',\n  description: '...' }"]
    h1 --> h2
  end

  %% ─────────────────────────────────────────────────────
  subgraph DOCKER ["🐳 STEP 3 — Docker Networking"]
    direction TB
    d1["frappe-helpdesk-docker/docker-compose.yml\n─────────────────\nDefines all containers:\n  • backend (Python app)\n  • frontend (Nginx serving built JS)\n  • db (MariaDB)\n  • redis-cache\n  • redis-queue\n  • redis-socketio\n  • websocket (Node.js)\nMaps port 8000 on your machine\nto the Nginx container's port 80."]
    d2["Nginx (inside backend container)\n─────────────────\nActs as a reverse proxy.\nReads the 'Host' header.\nForwards to the Gunicorn Python process\nvia UNIX socket."]
    d1 --> d2
  end

  %% ─────────────────────────────────────────────────────
  subgraph WSGI ["⚙️ STEP 4 — Python WSGI Server"]
    direction TB
    w1["Gunicorn\n─────────────────\nA Python web server that runs\nmultiple worker processes in parallel.\nReceives the raw HTTP request bytes."]
    w2["frappe/app.py → application()\n─────────────────\nFrappe's main WSGI entry point.\nConverts HTTP bytes into a Python dict.\nCalls frappe.init(site='helpdesk.localhost')\n  ↳ Loads site config from sites/helpdesk.localhost/\nCalls frappe.connect()\n  ↳ Opens MariaDB connection\n  ↳ Opens Redis cache connection"]
    w1 --> w2
  end

  %% ─────────────────────────────────────────────────────
  subgraph AUTH ["🔐 STEP 5 — Authentication & Session"]
    direction TB
    a1["helpdesk/auth.py → authenticate()\n─────────────────\nCustom auth hook registered in hooks.py.\nRuns before every single request.\nChecks if 'sid' cookie is valid."]
    a2["frappe/auth.py → HTTPRequest\n─────────────────\nReads Cookie: sid=abc123\nLooks up MariaDB 'tabSessions'\nOR Redis cache for that session ID.\nIf found → sets frappe.session.user = 'sarah@acme.com'\nIf not → redirect to /login"]
    a3["frappe.get_roles('sarah@acme.com')\n─────────────────\nLoads Sarah's roles from tabHasRole:\n  → ['HD Customer', 'Customer Member']\nThese roles determine what she can see/edit."]
    a1 --> a2 --> a3
  end

  %% ─────────────────────────────────────────────────────
  subgraph HANDLER ["🔀 STEP 6 — API Router"]
    direction TB
    r1["frappe/handler.py → handle()\n─────────────────\nFrappe's central URL dispatcher.\nParses: /api/method/helpdesk.api.doc.create_doc\nChecks @frappe.whitelist() decorator on function.\nIf not whitelisted → 403 Forbidden.\nIf whitelisted → calls the function."]
    r2["helpdesk/api/doc.py → create_doc()\n─────────────────\nThe entry point for creating any document.\nReceives the JSON body as Python kwargs.\nChecks permissions.\nPasses data through the field sanitizer.\nCalls frappe.new_doc() + doc.insert()"]
    r1 --> r2
  end

  %% ─────────────────────────────────────────────────────
  subgraph SANITIZER ["🛡️ STEP 7 — Field Security Sanitizer"]
    direction TB
    f1["helpdesk/ticket_fields.py → TicketFields\n─────────────────\nA security barrier class.\nAsked: 'Which fields is this session user allowed to see/set?'\n\nIf Sarah (customer):\n  Removes: _assign, sla, response_by, resolution_by,\n           feedback_rating, agent_group, and any field\n           where visible_to == 'Agents'\nIf Alex (agent):\n  Passes all fields through unchanged.\n\nPrevents customers from injecting\nagent-only fields into their request body."]
    f2["helpdesk/consts.py\n─────────────────\nHolds constants like:\n  CORE_TICKET_FIELDS — the base fields every ticket has\n  DEFAULT_TICKET_TEMPLATE — the default form template name\n  SERVER_COMPUTED_FIELDS — fields set only by the server"]
    f1 -.reads constants from.-> f2
  end

  %% ─────────────────────────────────────────────────────
  subgraph CONTROLLER ["🏗️ STEP 8 — HD Ticket Controller Lifecycle"]
    direction TB
    c0["frappe.new_doc('HD Ticket')\n─────────────────\nCreates an in-memory Python object.\nNothing is in the database yet."]
    c1["HDTicket.before_insert()\n─────────────────\nCalled BEFORE the first database write.\n→ generate_key(): Creates a UUID4 secret token.\n   This is used later for tokenized CSAT feedback emails.\n→ apply_ticket_insert_rules(): Checks any intake overrides."]
    c2["HDTicket.before_validate()\n─────────────────\n→ set_ticket_type(): Sets category (e.g. 'Technical Issue')\n→ set_raised_by(): Sets raised_by = 'sarah@acme.com'\n→ set_priority(): Reads default priority from HD Settings\n→ set_default_status(): Sets status = 'Open'\n→ set_status_category(): Sets category to 'Open' / 'Paused' / 'Resolved'\n→ validate_portal_contact(): Blocks Sarah from setting\n   someone else's contact on her ticket.\n→ set_contact(): Links Sarah's Contact record\n→ set_customer(): Auto-links 'Acme Corp' from the contact"]
    c3["hd_service_level_agreement/utils.py → get_sla()\n─────────────────\nEvaluates ALL active SLA policies in order:\n  1. Fetches all enabled SLAs from tabHD Service Level Agreement\n  2. Joins with tabHD Service Level Priority to find ones that\n     cover 'Urgent' priority.\n  3. Evaluates each SLA's 'condition' using frappe.safe_eval()\n     (safe Python evaluation, like: doc.customer == 'Acme Corp')\n  4. Returns the first matching SLA.\n  → Sets self.sla = 'Enterprise-SLA'"]
    c4["HDTicket.before_save()\n─────────────────\n→ set_resolution_date(): If resolving, stamp the timestamp.\n→ apply_sla(): Reads working hours from tabHD Service Day\n   and holidays from tabHD Service Holiday List.\n   Calculates:\n     response_by = now + 1h (skipping non-working hours)\n     resolution_by = now + 4h (skipping non-working hours)\n→ handle_email_feedback(): If status changed to 'Closed',\n   prepares a CSAT email with the UUID token URL."]
    c5["HDTicket.validate()\n─────────────────\n→ validate_feedback(): If settings require feedback before\n   resolving, checks that a rating was submitted."]
    c6["helpdesk/extends/comment.py\n─────────────────\nA doc_event hook on the Comment DocType.\nBefore any Comment is inserted:\n  → If it's on an HD Ticket AND it's a 'Comment' type:\n    → If session user is NOT an agent → throw PermissionError\nThis prevents customers from adding internal comments."]
    c7["helpdesk/overrides/realtime.py\n─────────────────\nOverrides Frappe's default realtime permission check.\nEnsures agents can only subscribe to rooms\nfor tickets they have permission to read."]
    c8["helpdesk/overrides/email_account.py → CustomEmailAccount\n─────────────────\nOverrides the default Email Account DocType behavior.\nCustomizes how incoming emails are processed\nand linked to HD Tickets as threads."]
    c9["helpdesk/overrides/assignment_rule.py → HelpdeskAssignmentRule\n─────────────────\nOverrides Frappe's Assignment Rule DocType.\nAdds helpdesk-specific logic:\n  → Checks agent availability (Online/Busy/Offline)\n  → Filters agents by team membership\n  → Applies round-robin or load-balancing distribution\n  → Calls HDTicket.assign_agent() on the winner"]
    c10["helpdesk/overrides/user_invitation.py → HelpdeskUserInvitation\n─────────────────\nOverrides the user invite flow.\nWhen someone accepts an invitation to join as an HD Customer,\nautomatically links them to the right HD Customer record."]

    c0 --> c1 --> c2 --> c3 --> c4 --> c5
    c9 -.runs after ticket is saved.-> c4
  end

  %% ─────────────────────────────────────────────────────
  subgraph DATABASE ["🗄️ STEP 9 — Database Write (MariaDB)"]
    direction TB
    db1["frappe.model.document.Document.insert()\n─────────────────\nCalls all lifecycle hooks in order.\nAfter all validations pass:\n  Converts the Python dict to SQL using PyPika query builder."]
    db2["SQL generated by frappe.qb (PyPika)\n─────────────────\nINSERT INTO tabHD Ticket (\n  name, subject, status, status_category,\n  priority, raised_by, customer, sla,\n  response_by, resolution_by, creation\n) VALUES (\n  '0042', '502 Error...', 'Open', 'Open',\n  'Urgent', 'sarah@acme.com', 'Acme Corp', 'Enterprise-SLA',\n  '2026-10-12 17:26', '2026-10-12 20:26', NOW()\n)"]
    db3["frappe.db.commit()\n─────────────────\nCommits the MariaDB transaction.\nData is now permanently persisted on disk.\nAll subsequent reads will see this new row."]
    db4["helpdesk/hooks.py → permission_query_conditions\n─────────────────\nRegistered SQL condition appended to ALL HD Ticket queries:\nhelpdesk.helpdesk.doctype.hd_ticket.hd_ticket.permission_query\nEnsures customers only see their own tickets.\nAgents see all tickets (or filtered by team if restricted)."]

    db1 --> db2 --> db3
    db4 -.appended to every SELECT query.-> db2
  end

  %% ─────────────────────────────────────────────────────
  subgraph POST_COMMIT ["⚡ STEP 10 — After Insert: Automations Fire"]
    direction TB
    p1["HDTicket.after_insert()\n─────────────────\nRuns AFTER the row is committed to database.\n→ capture_ticket_created_telemetry_events()\n→ tag_first_ticket(): Tags 'First Ticket' for new users\n→ create_communication_via_contact(): Creates the first\n   Communication record from the description text\n→ handle_inline_media_new_ticket(): Attaches any embedded\n   images from description to the ticket record\n→ send_acknowledgement_email(): If configured in HD Settings"]
    p2["frappe.enqueue('frappe.sendmail')\n─────────────────\nDoes NOT send the email immediately.\nPushes a job dict to Redis Queue:\n  redis-queue:6379\nThis is an async job that will run in the background.\nReturns immediately so the HTTP response is not blocked."]
    p3["helpdesk/utils.py → publish_event()\n─────────────────\nCalls frappe.publish_realtime('helpdesk:new-ticket')\nThis pushes a message to Redis Pub/Sub:\n  redis-socketio:6379\nThe message is: { event: 'helpdesk:new-ticket' }"]

    p1 --> p2
    p1 --> p3
  end

  %% ─────────────────────────────────────────────────────
  subgraph HOOKS ["🪝 STEP 11 — hooks.py: The Event Registry"]
    direction TB
    hk1["helpdesk/hooks.py\n─────────────────\nThis is Frappe's wiring file. It registers:\n\ndoc_events: What Python functions run when Frappe\n  core documents fire events:\n  • Comment.before_insert → extends/comment.py\n  • Comment.validate → extends/comment.py\n  • Assignment Rule.validate → extends/assignment_rule.py\n  • Customer.after_insert → integrations/erpnext/customer.py\n  • Notification Log.before_insert → extends/notification_log.py\n\nscheduler_events: Cron jobs:\n  • hourly_long: update_sla_status_in_ticket\n  • daily: close_tickets_after_n_days\n  • all: build_index_if_not_exists\n\noverride_doctype_class:\n  • Email Account → overrides/email_account.py\n  • Assignment Rule → overrides/assignment_rule.py\n  • User Invitation → overrides/user_invitation.py\n\npermission_query_conditions:\n  • HD Ticket → permission_query (row-level security)\n  • HD Customer → permission_query\n  • HD Saved Reply → permission_query\n\nhas_permission: Doc-level permission checks per DocType\nauth_hooks: helpdesk/auth.py runs on every request\nafter_install: helpdesk/setup/install.py setup_complete()"]
  end

  %% ─────────────────────────────────────────────────────
  subgraph BACKGROUND ["🔄 STEP 12 — Redis Background Workers"]
    direction TB
    bg1["Redis Queue (redis-queue:6379)\n─────────────────\nA task queue. Jobs are pushed in and\npicked up by background worker processes.\nPrevents slow tasks from blocking web responses."]
    bg2["Bench RQ Worker Process\n─────────────────\nA separate Python process that runs always.\nPolls the Redis queue for new jobs.\nPicks up the 'sendmail' job.\nRenders the Jinja email template."]
    bg3["hd_settings/helpers.py → get_default_email_content()\n─────────────────\nReturns the default Jinja HTML template\nfor different email types:\n  • 'acknowledgement': 'We received your ticket #0042'\n  • 'reply_via_agent': Agent reply email wrapper\n  • 'share_feedback': CSAT rating email\n  • 'reply_to_agents': Notify agent of customer reply"]
    bg4["SMTP Server → Email Delivered to sarah@acme.com\n─────────────────\nSubject: 'Ticket #0042: We've received your request'\nBody: rendered HTML with ticket details"]

    bg1 --> bg2 --> bg3 --> bg4
  end

  %% ─────────────────────────────────────────────────────
  subgraph REALTIME ["📡 STEP 13 — Socket.IO Real-time Pipeline"]
    direction TB
    rt1["Redis Pub/Sub (redis-socketio:6379)\n─────────────────\nA message bus. Backend publishes events.\nNode.js server subscribes and forwards them."]
    rt2["helpdesk/realtime/index.js\n(Node.js Socket.IO Server)\n─────────────────\nA separate Node.js process (not Python).\nSubscribes to Redis channel 'redis-socketio'.\nWhen a message arrives:\n  → Determines which browser clients should receive it\n  → Emits a WebSocket frame to those clients"]
    rt3["WebSocket Frame (WSS)\n─────────────────\nBinary/text frame travels over the network:\n  Event: 'helpdesk:new-ticket'\n  Data: {}\n\nOnly connected browsers in the 'helpdesk' room receive this."]
    rt1 --> rt2 --> rt3
  end

  %% ─────────────────────────────────────────────────────
  subgraph BROWSER_ALEX ["🖥️ STEP 14 — Alex's Browser Reacts"]
    direction TB
    al1["desk/src/socket.ts → initSocket()\n─────────────────\nCreates and manages the Socket.IO client connection.\nReads socketio_port from sites/common_site_config.json\nConnects to: http://helpdesk.localhost:9000/helpdesk.localhost\nRegisters all event listeners."]
    al2["desk/src/stores/globalStore.ts\n─────────────────\nHolds the shared $socket reference.\nAll Pinia stores import $socket from here\nto listen to real-time events."]
    al3["desk/src/stores/notification.ts → useNotificationStore\n─────────────────\nListens to: socket events for new notifications\nOn 'helpdesk:new-ticket':\n  → Increments the unread notification badge count\n  → Adds the notification to the bell dropdown list\nOn bell click → markSeen() clears badge."]
    al4["desk/src/stores/docTickets.ts → getTicketListResource()\n─────────────────\nManages the ticket list data via createListResource():\n  doctype: 'HD Ticket'\n  fields: [name, subject, status, priority,\n           _assign, response_by, resolution_by]\n  orderBy: 'modified desc'\nOn 'helpdesk:new-ticket' socket event:\n  → calls ticketsListResource.reload()\n  → fetches fresh ticket list from backend"]
    al5["desk/src/stores/sla.ts → useSlaStore\n─────────────────\nAfter the new ticket appears in the list:\n  → Reads response_by and resolution_by timestamps\n  → Computes: 'Response due in 59m'\n  → Drives the colored countdown pill on ticket cards\n  → Refreshes every 60 seconds automatically"]
    al6["desk/src/pages/home/Home.vue\n─────────────────\nThe agent dashboard page.\nDisplays:\n  • My Tickets count\n  • SLA Alerts table (the table you see in your screenshot!)\n  • Avg. First Response metric\n  • Avg. Resolution metric\n  • Recent Activity feed\n  • Avg. Time Metrics chart (from api/dashboard.py)\n  • Reviews / CSAT chart\nAll data comes from helpdesk/api/dashboard.py"]
    al7["desk/src/pages/ticket/Tickets.vue\n─────────────────\nThe main ticket list page.\nUses ListViewBuilder.vue to render the table.\nFilters, sorts, groups by any column.\nCalls api/doc.py → get_list_data() for data.\nCalls api/doc.py → get_filterable_fields() for filter options."]
    al8["desk/src/components/ListViewBuilder.vue\n─────────────────\nA generic, powerful data table component.\nRenders columns, handles click-to-sort,\ndrag-to-resize columns, row selection,\nbulk actions, and pagination."]
    al9["Browser DOM Repainted ✅\n─────────────────\nVue 3's reactivity system detects the store change.\nRuns a Virtual DOM diff algorithm.\nOnly updates the specific DOM nodes that changed.\nTicket #0042 appears in Alex's SLA Alerts table\nwith an URGENT badge — in real time."]

    al1 --> al2 --> al3
    al2 --> al4 --> al5 --> al6
    al4 --> al7 --> al8 --> al9
    al3 -.triggers reload.-> al4
  end

  %% ─────────────────────────────────────────────────────
  subgraph AGENT_ACTIONS ["👨‍💻 STEP 15 — Alex Opens & Responds to the Ticket"]
    direction TB
    aa1["desk/src/pages/ticket/TicketAgent.vue\n─────────────────\nThe full ticket detail page for agents.\nSplit-pane layout:\n  LEFT: Conversation thread\n  RIGHT: Ticket metadata (customer, priority, SLA, assignments)\nLoads ticket via createDocumentResource({ doctype: 'HD Ticket', name: '0042' })"]
    aa2["desk/src/pages/ticket/TicketConversation.vue\n─────────────────\nShows the chronological thread:\n  • Customer messages\n  • Agent replies\n  • Internal notes (yellow background, agents only)\n  • System activity logs (assigned, status changed)\nData comes from: helpdesk/api/timeline.py → get_comment_extras()"]
    aa3["desk/src/components/EmailEditor.vue\n─────────────────\nThe rich text email composer at the bottom.\nFeatures:\n  • TipTap-powered WYSIWYG editor (desk/src/tiptap-extensions.ts)\n  • CC / BCC fields (EmailMultiSelect.vue)\n  • Attachment uploads (AttachmentList.vue)\n  • Saved Replies picker (SavedRepliesSelectorModal.vue)\n  • From email selector\n  • Send button"]
    aa4["desk/src/components/SavedRepliesSelectorModal.vue\n─────────────────\nLets agents search and insert pre-written replies.\nFetches from: helpdesk/api/saved_replies.py\nEach reply can have Jinja variables like {{ doc.customer }}\nwhich are replaced with actual ticket values on insert."]
    aa5["HDTicket.reply_via_agent() [agent_only]\nhelpdesk/doctype/hd_ticket/hd_ticket.py\n─────────────────\nWhen Alex clicks Send:\n  1. Checks @agent_only decorator (helpdesk/utils.py)\n  2. Creates a Communication record (Sent)\n  3. Sets In-Reply-To header to the last threadable communication\n  4. Resolves sender email account\n  5. Calls frappe.sendmail() → queued to Redis\n  6. Calls HDTicket.publish_update() → WebSocket to Sarah's browser\nSarah's portal refreshes and shows Alex's reply."]
    aa6["desk/src/components/ticket-agent/\n─────────────────\nA directory of sub-components for the agent ticket view:\n  • TicketAgentDetails.vue: Priority, Type, SLA sidebar\n  • TicketAgentCustomer.vue: Contact & customer profile panel\n  • TicketAgentActivities.vue: The timeline/audit log\n  • TicketAgentActions.vue: Assign, escalate, merge buttons"]

    aa1 --> aa2 --> aa3 --> aa4 --> aa5
    aa1 --> aa6
  end

  %% ─────────────────────────────────────────────────────
  subgraph KB ["📚 STEP 16 — Knowledge Base (Deflection System)"]
    direction TB
    kb1["desk/src/pages/knowledge-base/KnowledgeBaseCustomer.vue\n─────────────────\nCustomer-facing KB homepage.\nShows categories, featured articles.\nSearch bar calls: helpdesk/api/search.py"]
    kb2["helpdesk/search_sqlite.py → HelpdeskSearch\n─────────────────\nMaintains a SQLite database as a Full-Text Search index.\nWhy SQLite? MariaDB LIKE queries are slow on large text.\nSQLite FTS5 is extremely fast for keyword search.\n\nBackground job (registered in hooks.py 'all' scheduler):\n  build_index_if_not_exists()\n  → Reads all published HD Articles from MariaDB\n  → Inserts titles + body into SQLite FTS table\n  → Updates index when articles change"]
    kb3["helpdesk/api/search.py\n─────────────────\nWhen customer types in the search bar:\n  → Receives the search query string\n  → Expands synonyms using HD Synonym records\n  → Removes stopwords using HD Stopword records\n  → Runs FTS query against SQLite index\n  → Returns matching article titles + snippets\n\nDeflection: If customer finds the answer here,\nthey don't need to create a ticket."]
    kb4["desk/src/pages/knowledge-base/Article.vue\n─────────────────\nRenders the full article in a readable format.\nShows thumbs up/down feedback buttons.\nFeedback saved to: tabHD Article Feedback"]
    kb1 --> kb2 --> kb3 --> kb4
  end

  %% ─────────────────────────────────────────────────────
  subgraph SCHEDULER ["⏰ STEP 17 — Scheduled Background Jobs"]
    direction TB
    sc1["helpdesk/hooks.py → scheduler_events\n─────────────────\nRegisters cron-style jobs with Frappe's scheduler.\nBench's background worker runs these automatically."]
    sc2["HOURLY: update_sla_status_in_ticket()\nhelpdesk/doctype/hd_ticket/hd_ticket.py\n─────────────────\nScans all Open tickets.\nFor each ticket:\n  → Checks if response_by has passed without a response\n  → Checks if resolution_by has passed\n  → If either is breached: sets agreement_status = 'Failed'\n  → This makes the ticket appear in SLA Alerts with red color"]
    sc3["DAILY: close_tickets_after_n_days()\nhelpdesk/doctype/hd_ticket/hd_ticket.py\n─────────────────\nFinds Resolved tickets where the customer\nhas not replied for N days (set in HD Settings).\nAutomatically moves them to 'Closed' status."]
    sc4["ALL: build_index_if_not_exists()\nhelpdesk/search.py\n─────────────────\nChecks if the SQLite search index is built.\nIf not, triggers index build in a background job.\nAlso downloads synonym corpus from external source."]
    sc1 --> sc2
    sc1 --> sc3
    sc1 --> sc4
  end

  %% ─────────────────────────────────────────────────────
  subgraph ERPNEXT ["🔗 STEP 18 — ERPNext Integration"]
    direction TB
    er1["helpdesk/integrations/erpnext/customer.py\n─────────────────\nA doc_event hook registered on Frappe's built-in 'Customer' DocType.\nWhen an ERPNext Customer is created/updated:\n  → Syncs it as an HD Customer record\n  → Links contacts and members\n  → Maintains two-way name sync on rename"]
    er2["helpdesk/integrations/erpnext/user_permission.py\n─────────────────\nWhen a User Permission is created/changed in ERPNext:\n  → Syncs access rules to HD Customer\n  → Ensures the customer portal shows correct customer scope"]
    er3["helpdesk/integrations/erpnext/mirror_sync.py\n─────────────────\nHandles bulk synchronization between ERPNext and Helpdesk.\nUsed during initial setup or after ERPNext customer data changes."]
    er4["erpnext_hd_settings DocType\nhelpdesk/helpdesk/doctype/erpnext_hd_settings/\n─────────────────\nA settings form in Frappe Desk for configuring:\n  • Is ERPNext sync enabled?\n  • Which ERPNext site to sync from?\n  • Field mapping overrides"]
    er1 --> er2 --> er3 --> er4
  end

  %% ─────────────────────────────────────────────────────
  subgraph ANALYTICS ["📊 STEP 19 — Analytics & Dashboard Data"]
    direction TB
    an1["helpdesk/api/dashboard.py\n─────────────────\nProvides all data for the agent home dashboard:\n  • get_ticket_counts(): My Tickets, Open count\n  • get_first_response_metrics(): Avg first response time\n  • get_resolution_metrics(): Avg resolution time\n  • get_sla_summary(): SLA compliance %\n  • get_recent_activity(): What the current agent did lately\n  • get_ticket_trends(): Tickets over time (for line chart)\n  • get_overview(): Summary KPIs for reporting period"]
    an2["helpdesk/api/ticket_analytics.py\n─────────────────\nDeeper analytics per agent, per team, per period:\n  • Resolution time distribution\n  • First response time distribution\n  • Ticket volume by priority / type / team\n  • CSAT scores aggregated by period\n  • SLA breach breakdown"]
    an3["helpdesk/api/analytics_utils.py\n─────────────────\nShared utility functions for analytics queries:\n  • Date range builders\n  • Group-by aggregators\n  • Time-bucket functions (daily, weekly, monthly)"]
    an1 --> an2 --> an3
  end

  %% ─────────────────────────────────────────────────────
  %% FLOW CONNECTIONS BETWEEN STAGES
  BROWSER_SARAH --> HTTP_LAYER
  HTTP_LAYER --> DOCKER
  DOCKER --> WSGI
  WSGI --> AUTH
  AUTH --> HANDLER
  HANDLER --> SANITIZER
  SANITIZER --> CONTROLLER
  CONTROLLER --> DATABASE
  DATABASE --> POST_COMMIT
  POST_COMMIT --> BACKGROUND
  POST_COMMIT --> REALTIME
  REALTIME --> BROWSER_ALEX
  HOOKS -.wires everything.-> CONTROLLER
  HOOKS -.wires everything.-> DATABASE
  HOOKS -.wires everything.-> SCHEDULER
  SCHEDULER -.runs periodically.-> DATABASE
  BROWSER_ALEX --> AGENT_ACTIONS
  BROWSER_SARAH -.customer portal.-> KB
  ERPNEXT -.syncs customer data.-> DATABASE
  AGENT_ACTIONS --> DATABASE
  ANALYTICS -.feeds dashboard.-> BROWSER_ALEX
```

---

## 📁 Complete File-by-File Reference Table

Below is every important file in the repo, grouped by location, with a plain-English explanation of its role.

---

### 🟦 FRONTEND (`helpdesk/desk/`)

| File | What it does |
|:-----|:-------------|
| `desk/src/main.js` | **The starting gun.** Creates the Vue app, installs Pinia (state management), Vue Router, frappe-ui library, Socket.IO connection, and mounts the app onto `#app` in the HTML. The very first JavaScript that runs. |
| `desk/src/App.vue` | **The root Vue component.** Just a `<RouterView>` that tells Vue "render whatever page the current URL maps to". |
| `desk/src/index.css` | **Global CSS styles and Tailwind token imports.** Defines colors like `bg-surface-white`, fonts, and base spacing. |
| `desk/src/types.ts` | **TypeScript shape definitions.** Defines what a `Ticket`, `Agent`, `SLA`, `Notification` object looks like in JavaScript, so the editor can catch type errors. |
| `desk/src/socket.ts` | **WebSocket connection.** Uses Socket.IO client to connect to the Node.js realtime server. Reads the port number from `common_site_config.json`. Exported as a singleton `socket` used throughout the app. |
| `desk/src/persona.ts` | **Onboarding guard.** Detects if the admin user has not yet done first-time setup (selected their persona). Redirects to the `/onboarding` page if needed. |
| `desk/src/telemetry.ts` | **Usage analytics.** Sends anonymous events (ticket created, replied, etc.) to Frappe's telemetry system. Can be opted out of. |
| `desk/src/translation.ts` | **i18n (internationalization) plugin.** Registers Frappe's `__()` translation function so UI text can be displayed in the user's language. |
| `desk/src/tiptap-extensions.ts` | **Rich text editor extensions.** Configures the TipTap WYSIWYG editor with email-safe formatting: mentions (`@user`), attachments, images, code blocks, etc. |
| `desk/src/router/index.ts` | **URL → Page mapping.** Defines every URL route in the app. Also runs **before navigation guards** that check: Is this user logged in? Are they an agent or customer? Redirects accordingly. |
| `desk/src/roots/PortalRoot.vue` | **Portal switcher.** Checks `authStore.isAgent`. If yes → load `AgentRoot.vue` (agent shell). If no → load `CustomerPortalRoot.vue` (customer shell). |
| `desk/src/roots/AgentRoot.vue` | **Agent shell layout.** The sidebar navigation, header, notification bell, availability toggle — everything agents see around every page. |
| `desk/src/roots/CustomerPortalRoot.vue` | **Customer shell layout.** Simpler layout with just the customer's portal navigation. |
| `desk/src/stores/auth.ts` | **Session state.** Fetches the current user's profile, roles, agent status, team, and availability from `helpdesk.api.auth.get_user`. All other stores read from here to check "who is this user". |
| `desk/src/stores/sla.ts` | **SLA countdown engine.** Reads `response_by` and `resolution_by` timestamps from tickets. Computes how much time remains. Drives the countdown pill (e.g., "Response due in 47m") seen on tickets. |
| `desk/src/stores/docTickets.ts` | **Ticket list data layer.** Creates the `createListResource` for HD Ticket list views. Manages pagination, filters, and reload on socket events. |
| `desk/src/stores/agentStatus.ts` | **Agent availability toggle.** Manages Online / Busy / Offline state. Persists to the `HD Agent` record via API. Other agents see your availability for assignment rules. |
| `desk/src/stores/assignmentRules.ts` | **Assignment rule UI state.** Caches assignment rule data used in the ticket assignment dropdowns and settings pages. |
| `desk/src/stores/knowledgeBase.ts` | **KB category and article state.** Caches the category tree and current article for the knowledge base pages. |
| `desk/src/stores/notification.ts` | **Notification bell.** Counts unread notifications. Routes clicks to the correct ticket/comment. Marks all notifications as seen when the bell is opened. |
| `desk/src/stores/ticketStatus.ts` | **Status options.** Fetches all `HD Ticket Status` records (Open, Resolved, Closed etc.) so dropdowns can be populated. |
| `desk/src/stores/ticketPriority.ts` | **Priority options.** Fetches all `HD Ticket Priority` records (Low/Medium/High/Urgent) for dropdowns. |
| `desk/src/stores/meta.ts` | **DocType metadata.** Caches Frappe DocType field definitions for the ticket form so it knows field types, labels, and options. |
| `desk/src/stores/user.ts` | **User directory.** Fetches all agent users so that assignment dropdowns and @mention suggestions work. |
| `desk/src/pages/home/Home.vue` | **Agent Home Dashboard.** Shows SLA alerts table, my tickets count, average response time, average resolution time, recent activity feed, and charts. Data from `helpdesk/api/dashboard.py`. |
| `desk/src/pages/ticket/Tickets.vue` | **Ticket list page.** The full-featured ticket queue with filtering, sorting, grouping, bulk actions. Uses `ListViewBuilder.vue`. |
| `desk/src/pages/ticket/TicketNew.vue` | **Create ticket form.** Used by both agents and customers. Loads the ticket template fields from `ticket_fields.py`. On submit, calls `helpdesk.api.doc.create_doc`. |
| `desk/src/pages/ticket/TicketAgent.vue` | **Agent ticket detail view.** Full split-pane view of an open ticket for agents: conversation thread + metadata sidebar. |
| `desk/src/pages/ticket/TicketCustomer.vue` | **Customer ticket detail view.** Simplified view of a ticket for the customer portal: shows their own messages and agent replies only. |
| `desk/src/pages/ticket/TicketConversation.vue` | **The message thread.** Renders emails, agent replies, internal notes, and system activity logs in chronological order. |
| `desk/src/pages/ticket/TicketFeedback.vue` | **CSAT rating page.** The tokenized URL page (`/ticket-feedback/new?key=UUID`) where customers rate their experience. |
| `desk/src/pages/knowledge-base/` | **All KB pages.** Agent article editor, customer KB homepage, category browser, article reader. |
| `desk/src/pages/customer/` | **Customer organization profile pages.** Shows the customer's details and all their tickets. |
| `desk/src/pages/contact/` | **Contact profile pages.** Individual person profile with contact info and ticket history. |
| `desk/src/pages/dashboard/Dashboard.vue` | **Manager Analytics Dashboard.** Charts and metrics for supervisors: team performance, SLA compliance trends. |
| `desk/src/pages/call-logs/CallLogs.vue` | **Telephony call log viewer.** Lists inbound/outbound calls from the integrated telephony system. |
| `desk/src/components/EmailEditor.vue` | **The reply composer.** Full-featured email editor with TipTap, CC/BCC, attachments, and saved replies. |
| `desk/src/components/ListViewBuilder.vue` | **Reusable data table.** Powers every list view in the app (tickets, customers, contacts, KB articles). |
| `desk/src/components/TicketField.vue` | **Dynamic field renderer.** Renders any HD Ticket field based on its type (Link, Select, Date, etc.). Uses `ticket_fields.py` metadata. |
| `desk/src/components/CommunicationArea.vue` | **Email display widget.** Renders a single email communication with formatting, inline images, and reply button. |
| `desk/src/components/SavedRepliesSelectorModal.vue` | **Canned response picker.** Search modal for finding and inserting saved reply templates. |

---

### 🟩 BACKEND — API Endpoints (`helpdesk/helpdesk/api/`)

| File | What it does |
|:-----|:-------------|
| `api/auth.py` | **Who are you?** `get_user()` returns the logged-in user's full profile: name, roles, isAgent, isManager, team, availability. Called by `auth.ts` on every app load. |
| `api/doc.py` | **Generic DocType API.** The big one. Powers the ticket list, filtering, sorting, grouping, column configuration, and field metadata. `create_doc()` is the entry point when Sarah submits a ticket. |
| `api/ticket.py` | **Ticket-specific actions.** `assign_ticket_to_agent()`, `split_ticket()` — actions that are too specialized for `doc.py`. |
| `api/comment.py` | **Comment CRUD.** Create, edit, delete comments on tickets. Checks agent permissions before allowing. |
| `api/timeline.py` | **Ticket activity feed.** `get_comment_extras()` returns reactions, attachments, and pinned status for all comments on a ticket. `get_ticket_calls()` returns call log rows for the timeline. |
| `api/saved_replies.py` | **Canned responses.** Fetches saved reply templates, applies Jinja rendering to substitute `{{ doc.customer }}` type variables. |
| `api/knowledge_base.py` | **KB queries.** Get article categories, get articles in a category, vote on an article's helpfulness. |
| `api/search.py` | **Global search.** Calls the SQLite FTS engine to search across KB articles, tickets, and contacts. |
| `api/dashboard.py` | **Home dashboard data.** Provides all the metric cards and chart data seen on the agent home page. |
| `api/ticket_analytics.py` | **Deep analytics.** Resolution time distributions, SLA compliance rates, per-agent/per-team performance charts. |
| `api/analytics_utils.py` | **Analytics helper functions.** Shared utilities for building date-bucketed queries. |
| `api/customer.py` | **Customer org API.** Get customer details, linked contacts, and ticket history for the customer profile page. |
| `api/contact.py` | **Contact person API.** Get contact details, create contacts, link contacts to customers. |
| `api/agent_home/` | **Agent home-specific endpoints.** Data tailored specifically for the agent's personal dashboard view (my tickets, my SLA status). |
| `api/onboarding.py` | **First-run setup.** Tracks which onboarding steps ("Getting started" checklist) have been completed. |
| `api/permission.py` | **App-level permission check.** `has_app_permission()` — checked before showing the Helpdesk app in the Frappe app launcher. |
| `api/session.py` | **Session utilities.** Bootstrap data for the frontend. |
| `api/banners.py` | **Announcement banners.** Displays site-wide banners to customer portal users. |
| `api/settings/` | **Settings API.** Endpoints for reading and writing `HD Settings` configuration from the settings pages. |
| `api/tags.py` | **Ticket tags.** Create, apply, and list tags on tickets. |
| `api/general.py` | **Miscellaneous shared endpoints.** Small utility APIs. |

---

### 🟨 BACKEND — Core DocType Controllers (`helpdesk/helpdesk/doctype/`)

| DocType Directory | What it does |
|:------------------|:-------------|
| `hd_ticket/hd_ticket.py` | **THE core of the entire system.** Every ticket lifecycle event is handled here: insert, validate, save, update, delete. SLA application, email sending, auto-assignment, realtime publishing. |
| `hd_ticket/customer_edit_controller.py` | **Customer write guard.** Mixin class that prevents customers from editing fields they don't own on their tickets. |
| `hd_service_level_agreement/hd_service_level_agreement.py` | **SLA engine.** Calculates response and resolution deadlines, handles pause/resume on status changes, tracks breaches. |
| `hd_service_level_agreement/utils.py` | **SLA selector.** `get_sla(ticket)` — evaluates all active SLAs and returns the matching one for the given ticket. |
| `hd_team/hd_team.py` | **Team management.** When a team is created/updated, manages the linked Frappe `Assignment Rule` record automatically. |
| `hd_customer/hd_customer.py` | **Customer permission rules.** `permission_query` ensures customers only see their own tickets. `has_permission` enforces doc-level access. |
| `hd_agent/hd_agent.py` | **Agent record.** `has_permission` controls who can see agent profiles. `is_active` field gates auto-assignment eligibility. |
| `hd_article/hd_article.py` | **KB article controller.** Manages article publish status, increments view counter, validates category assignment. |
| `hd_saved_reply/hd_saved_reply.py` | **Saved replies + macros.** Handles team-scoped replies, Jinja rendering, and the macro action system (e.g., a reply that also changes ticket status). |
| `hd_settings/hd_settings.py` | **Global settings controller.** Singleton settings document. Validates configuration when saved. |
| `hd_settings/helpers.py` | **Email template helper.** `get_default_email_content(type)` returns the default Jinja HTML for each email type. |
| `hd_notification/` | **In-app notification records.** Each row is one notification for one user. Read by the bell dropdown. |
| `hd_ticket_activity/` | **Audit trail.** Records every action taken on a ticket (viewed, assigned, status changed) for the activity timeline. |
| `hd_ticket_comment/` | **Comment record.** Minimal controller — most comment logic lives in `extends/comment.py`. |

---

### 🟥 BACKEND — System Wiring Files (`helpdesk/helpdesk/`)

| File | What it does |
|:-----|:-------------|
| `hooks.py` | **The master wiring file.** Registers every event, override, scheduler job, and permission hook with Frappe. The first file you read to understand what plugs into what. |
| `utils.py` | **Shared helpers.** `is_agent()`, `is_admin()`, `agent_only` decorator, `publish_event()`, `get_customers()`, phone number parsing, call log formatting. |
| `ticket_fields.py` | **Field security gate.** `TicketFields` class determines which HD Ticket fields are visible to each user type. Enforces customer/agent boundary. |
| `consts.py` | **Constants.** `CORE_TICKET_FIELDS`, `DEFAULT_TICKET_TEMPLATE`, `SERVER_COMPUTED_FIELDS` — shared magic strings. |
| `auth.py` | **Custom authentication hook.** Runs on every request. Can block or allow access before normal Frappe auth runs. |
| `notifications.py` | **Notification dispatch.** `notify_ticket_reopened()` sends real-time and email notifications when a ticket is re-opened by a customer reply. |
| `search.py` | **Full-text search coordinator.** `build_index_in_background()`, `build_index_if_not_exists()`, `download_corpus()`. |
| `search_sqlite.py` | **SQLite FTS engine.** `HelpdeskSearch` class. Maintains the SQLite database for fast full-text article search. |
| `extends/comment.py` | **Comment rules.** `before_insert` blocks non-agents from adding comments. `validate` caps pinned comments at 5. `has_permission` hides internal comments from customers. |
| `extends/assignment_rule.py` | **Assignment rule extension.** Validates assignment rules when saved. Cleans up when deleted. |
| `extends/notification_log.py` | **Notification routing.** `before_insert` on Notification Log — filters out notification types that should not generate emails (e.g., emoji reactions). |
| `overrides/assignment_rule.py` | **HelpdeskAssignmentRule.** Replaces Frappe's default Assignment Rule behavior with helpdesk-aware agent selection (availability + team check). |
| `overrides/email_account.py` | **CustomEmailAccount.** Customizes how Frappe processes incoming emails — routes them to HD Ticket as threaded communications. |
| `overrides/realtime.py` | **Realtime permission check.** Ensures agents can only subscribe to WebSocket rooms for tickets they are authorized to see. |
| `overrides/user_invitation.py` | **HelpdeskUserInvitation.** After a customer accepts an invite, links them to the correct HD Customer record. |
| `integrations/erpnext/customer.py` | **ERPNext Customer sync.** Mirrors ERPNext Customer create/update/rename/delete into HD Customer. |
| `integrations/erpnext/user_permission.py` | **ERPNext permission sync.** When ERPNext user permissions change, syncs customer-scoped access to Helpdesk. |
| `integrations/erpnext/mirror_sync.py` | **Bulk ERPNext sync.** Synchronizes all ERPNext customer data in bulk (used during setup). |
| `setup/install.py` | **Post-install setup.** `after_install()` — runs when the Helpdesk app is first installed. Creates default statuses, priorities, SLAs, and seed data. |

---

## 🧠 Mental Model Summary

Think of the whole system in these 5 layers:

```
┌──────────────────────────────────────────┐
│  1. BROWSER (Vue 3 SPA)                  │
│  What the user sees and interacts with   │
│  Files: desk/src/**                      │
├──────────────────────────────────────────┤
│  2. HTTP TRANSPORT                       │
│  JSON over HTTPS, Cookie authentication  │
│  Library: frappe-ui → fetch()            │
├──────────────────────────────────────────┤
│  3. PYTHON BACKEND (Frappe Framework)    │
│  Business logic, permissions, SLA engine │
│  Files: helpdesk/helpdesk/**             │
├──────────────────────────────────────────┤
│  4. DATABASE (MariaDB + SQLite)          │
│  All persistent data storage             │
│  Schema defined by DocType JSON files    │
├──────────────────────────────────────────┤
│  5. INFRASTRUCTURE (Docker/Redis/Node)   │
│  Networking, async jobs, realtime events │
│  Files: docker-compose.yml, socket.ts    │
└──────────────────────────────────────────┘
```

Every feature you build will touch at least 3 of these 5 layers.
Every bug you chase will be in exactly one of these 5 layers.

---

*This document is your complete architectural reference. Every file that exists in this repo has a row in this guide.*
