"""Static content of the public site beyond the installed products: the navigation, the information pages and the
products that are announced but NOT installed.

Presentation only. Nothing here grants access or creates anything, and nothing here is a registry entry: a product
that is not installed is shown only as "Coming soon", with no sign-up, no sign-in and no link into an application.
When a product is installed and registered (`nxerp.registry`), its registry entry replaces its announcement here.

Copy rules (docs/design/ui-contract.md): short, calm, sentence case, no customer counts, awards, certifications or
uptime figures, and no claim the platform cannot prove today.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Upcoming:
	key: str
	title: str
	tagline: str
	summary: str
	features: tuple
	logo: str
	mark: str
	category: str = "Business apps"


UPCOMING: tuple = (
	Upcoming(
		key="aira-hrms",
		title="AIRA HRMS",
		tagline="AI-powered HR and workforce intelligence",
		summary=(
			"AIRA, Adaptive Intelligence for Resource Automation, is the planned HR and workforce product for NXDESK. "
			"It is not installed on this site yet."
		),
		features=(
			"People records and structure",
			"Attendance and leave",
			"Workforce reporting",
			"AI-assisted insights",
		),
		logo="/assets/nxerp/images/aira-hrms-logo.png",
		mark="/assets/nxerp/images/aira-hrms-mark.png",
	),
)

# SVG path data for the 24px stroke icons used by the information pages
ICONS = {
	"key": '<circle cx="8" cy="15" r="4"/><path d="m10.8 12.2 8.7-8.7M15.5 7.5l2.5 2.5M18 5l2.5 2.5"/>',
	"shield": '<path d="M12 2.8 4.5 5.7v5.6c0 4.6 3.1 8.4 7.5 9.9 4.4-1.5 7.5-5.3 7.5-9.9V5.7L12 2.8Z"/><path d="m8.8 12 2.2 2.2 4.3-4.4"/>',
	"grid": '<rect x="3.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.8"/>',
	"sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
	"layers": '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 13 9 5 9-5"/>',
	"users": '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><path d="M16 5.2a3.2 3.2 0 0 1 0 5.6M18 14.4c2 .8 3.4 2.8 3.4 5.1"/>',
	"mail": '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="m3.5 7 8.5 6 8.5-6"/>',
	"chart": '<path d="M5 20V11M12 20V4M19 20v-7"/>',
	"headset": '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="14" width="4" height="6" rx="1.5"/><rect x="17" y="14" width="4" height="6" rx="1.5"/>',
	"book": '<path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5v-15Z"/><path d="M5 19.5A1.5 1.5 0 0 0 6.5 21H19v-3"/>',
	"building": '<rect x="4.5" y="3" width="15" height="18" rx="2"/><path d="M9 7.5h2M13 7.5h2M9 12h2M13 12h2M10 21v-4h4v4"/>',
	"globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.6 2.5 4 5.6 4 9s-1.4 6.5-4 9c-2.6-2.5-4-5.6-4-9s1.4-6.5 4-9Z"/>',
	"clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
	"check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
	"lock": '<rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
	"cart": '<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/><path d="M3 4h2.5l2.2 10.5h10.3L20 7H6.4"/>',
	"box": '<path d="M21 8 12 3 3 8l9 5 9-5Z"/><path d="M3 8v8l9 5 9-5V8M12 13v8"/>',
	"phone": '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z"/>',
	"pin": '<path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21Z"/><circle cx="12" cy="9.5" r="2.5"/>',
	"send": '<path d="M21 3 10 14M21 3l-7 18-4-7-7-4 18-7Z"/>',
	"handshake": '<path d="m11 17 2 2a1.4 1.4 0 0 0 2-2M14 14l2.5 2.5a1.4 1.4 0 0 0 2-2L15 11M8 12l3 3M3 12l5-5 4 1 3-3 6 6-3 3M3 12l3 3"/>',
	"list": '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>',
}

# Public business contact details, as published on Sria Infotech's own website (www.sriainfotech.com/contact). Presentation only.
# ASSUMPTION to confirm with the owner: which mailbox takes general enquiries (the company site lists sales@ for the contact section and
# hr@ next to each office). `nxerp_enquiry_email` in site config decides where submitted messages are emailed; without it they are only stored.
CONTACT = {
	"phone": "+91 90595 85039",
	"phone_href": "tel:+919059585039",
	"email": "sales@sriainfotech.com",
	"email_href": "mailto:sales@sriainfotech.com",
	"response": "We aim to reply within 24 hours.",
}

OFFICES = (
	{
		"name": "Hyderabad, Kondapur",
		"role": "Head office",
		"address": "303, 3rd Floor, Udaya Vensar Apartments, Rd Number 1, Hanuman Nagar, Kothaguda, Kondapur, Hyderabad, Telangana 500084, India",
		"phone": "+91 90595 85039",
	},
	{
		"name": "Hyderabad, T-Hub",
		"role": "Office",
		"address": "Plot No 1/C, Sy No 83/1, Raidurgam, Knowledge City Rd, Panmaktha, Hyderabad, Serilingampalle (M), Telangana 500032, India",
		"phone": "+91 90595 85039",
	},
	{
		"name": "Amaravati",
		"role": "Office",
		"address": "Amaravati, Andhra Pradesh 522503, India",
		"phone": "+91 95539 55893",
	},
	{
		"name": "Mulugu",
		"role": "Office",
		"address": "TASK Center, Mulugu, Telangana 506343, India",
		"phone": "+91 90145 52492",
	},
	{
		"name": "Pennsylvania",
		"role": "Office, USA",
		"address": "18 Hunters Dr, Gilbertsville, PA 19525-6601, USA",
		"phone": "+1 614 216 7070",
	},
)

# The information pages: slug -> content. Each block is a card: title, body, icon, and optionally a link.
PAGES = {
	"platform": {
		"eyebrow": "Platform",
		"title": "One platform for the applications your team uses",
		"lead": "NXDESK is the shared layer around your business applications: one sign-in, one place to open them, and one way to decide who may use what.",
		"blocks": (
			{
				"icon": "key",
				"title": "One sign-in",
				"body": "A person has one account and one password. Every application you are given opens with it.",
			},
			{
				"icon": "shield",
				"title": "Access by role",
				"body": "Administrators give roles. What someone can open follows those roles, and nothing else.",
			},
			{
				"icon": "grid",
				"title": "Your apps in one place",
				"body": "After signing in, people go straight to their application, or to a page listing the ones they can use.",
			},
			{
				"icon": "layers",
				"title": "Applications stay themselves",
				"body": "NXERP is built on ERPNext and Sria Helpdesk is a separate support application. They are connected, not merged.",
			},
			{
				"icon": "sun",
				"title": "Light and dark",
				"body": "Every public and sign-in screen follows your system theme, and you can switch it yourself.",
			},
			{
				"icon": "grid",
				"title": "Room for more",
				"body": "Adding an application means registering it once. The launcher, access rules and this site pick it up from there.",
			},
		),
		"sections": (
			{
				"type": "steps",
				"title": "From sign-up to working",
				"items": (
					{"title": "Create an account", "body": "Anyone can sign up with an email address and set a password from the link we send."},
					{"title": "Ask for an application", "body": "Pick a product and send an access request. It stays pending until someone decides."},
					{"title": "An administrator decides", "body": "Approval gives the role for that application. Refusal gives nothing."},
					{"title": "Open it from one place", "body": "After signing in, you land in your application, or on a page listing every one you may use."},
				),
			},
			{
				"type": "faq",
				"title": "Common questions",
				"items": (
					{"q": "Do I need a separate login for each application?", "a": "No. One account signs you in everywhere you have access."},
					{"q": "Does signing up give me access to the applications?", "a": "No. Creating an account only creates the account. Access to an application is a role an administrator gives."},
					{"q": "Are NXERP and Sria Helpdesk one program?", "a": "No. They are separate applications that keep their own data. NXDESK connects the sign-in and the way you open them."},
					{"q": "Can customers use Sria Helpdesk?", "a": "Yes, through the customer portal, which shows only their own requests."},
				),
			},
		),
		"cta": {"label": "Explore products", "href": "/products"},
	},
	"security": {
		"eyebrow": "Access and security",
		"title": "Access is decided on the server",
		"lead": "Hiding a link is not security. Every request is checked on the server, whatever the screen shows.",
		"blocks": (
			{
				"icon": "shield",
				"title": "Role-based grants",
				"body": "Access to an application is a role an administrator assigns. Removing the role removes the access on the next request.",
			},
			{
				"icon": "lock",
				"title": "Checked on every request",
				"body": "Pages, data calls and files are checked against the signed-in person's access, including direct links.",
			},
			{
				"icon": "users",
				"title": "Customers stay in the portal",
				"body": "A customer reaches only the customer portal. They never see the internal desk or internal ticket data.",
			},
			{
				"icon": "check",
				"title": "Requests are reviewed",
				"body": "Creating an account never grants staff access. An administrator reviews each access request and decides.",
			},
			{
				"icon": "book",
				"title": "A record without personal data",
				"body": "Refused requests are logged with a short hashed reference, never an email address or a name.",
			},
			{
				"icon": "key",
				"title": "Safe sign-in redirects",
				"body": "After signing in, a person is sent only to a place on this site that their access allows.",
			},
		),
		"sections": (
			{
				"type": "table",
				"title": "What is checked, and where",
				"head": ("Area", "How it works"),
				"rows": (
					("Sign-in", "One account. A password is set from an emailed link."),
					("Application access", "A role per application, checked on the server for every page and data call."),
					("Direct links", "Opening a link by hand gets the same check as a click. Hiding a button is never the control."),
					("Customers", "The customer portal only. No internal desk and no internal ticket data."),
					("Access requests", "Created as pending, decided by an administrator, and recorded."),
					("Refused requests", "Logged with a short hashed reference. The log holds no email address and no name."),
				),
			},
			{
				"type": "faq",
				"title": "Questions about access",
				"items": (
					{"q": "What happens when someone leaves?", "a": "An administrator removes their roles or disables the account. The change applies on their next request."},
					{"q": "Who can approve access?", "a": "Administrators of the platform."},
					{"q": "Where do I report a problem?", "a": "Write to us from the contact page and say which application it concerns."},
				),
			},
		),
		"cta": {"label": "How the platform works", "href": "/platform"},
	},
	"solutions": {
		"eyebrow": "Solutions",
		"title": "Start from the work your team does",
		"lead": "Pick the area you care about. Each one points to the product that covers it today, or says plainly that it is still to come.",
		"blocks": (
			{
				"icon": "chart",
				"title": "Finance and accounting",
				"body": "Accounts, invoicing and reporting in NXERP.",
				"href": "/products/erpnext",
				"cta": "NXERP",
			},
			{
				"icon": "cart",
				"title": "Sales and purchasing",
				"body": "Quotations, orders and suppliers in NXERP.",
				"href": "/products/erpnext",
				"cta": "NXERP",
			},
			{
				"icon": "box",
				"title": "Operations and stock",
				"body": "Stock, manufacturing, projects and assets in NXERP.",
				"href": "/products/erpnext",
				"cta": "NXERP",
			},
			{
				"icon": "headset",
				"title": "Customer support",
				"body": "Tickets, a knowledge base and service levels in Sria Helpdesk.",
				"href": "/products/helpdesk",
				"cta": "Sria Helpdesk",
			},
			{
				"icon": "users",
				"title": "People and HR",
				"body": "Planned as AIRA HRMS. Not installed yet.",
				"href": "/products/aira-hrms",
				"cta": "AIRA HRMS",
				"pill": "Coming soon",
			},
		),
		"sections": (
			{
				"type": "faq",
				"title": "Choosing where to start",
				"items": (
					{"q": "We run accounts and stock today. Where do we begin?", "a": "NXERP covers accounting, selling, buying, stock and manufacturing. Request access, then set up your company."},
					{"q": "We need to handle customer requests.", "a": "Sria Helpdesk gives your team tickets, a knowledge base and service levels, and your customers a portal."},
					{"q": "What about HR?", "a": "AIRA HRMS is announced and not installed yet. It is listed so you can see what is planned."},
					{"q": "Can I start with one and add another later?", "a": "Yes. Each application is requested on its own and opens from the same sign-in."},
				),
			},
		),
		"cta": {"label": "See all products", "href": "/products"},
	},
	"roadmap": {
		"eyebrow": "Roadmap",
		"title": "What is available and what comes next",
		"lead": "A plain list. Available means installed on this site and ready to be requested. Coming soon means announced, not installed.",
		"blocks": (
			{
				"icon": "chart",
				"title": "NXERP",
				"body": "Accounting, selling, buying, stock, manufacturing and projects.",
				"href": "/products/erpnext",
				"cta": "Learn more",
				"pill": "Available",
			},
			{
				"icon": "headset",
				"title": "Sria Helpdesk",
				"body": "Support tickets, knowledge base and service levels.",
				"href": "/products/helpdesk",
				"cta": "Learn more",
				"pill": "Available",
			},
			{
				"icon": "users",
				"title": "AIRA HRMS",
				"body": "HR and workforce product. Not installed on this site yet.",
				"href": "/products/aira-hrms",
				"cta": "Learn more",
				"pill": "Coming soon",
			},
		),
		"sections": (
			{
				"type": "table",
				"title": "At a glance",
				"head": ("Product", "Status", "Covers"),
				"rows": (
					("NXERP", "Available", "Accounting, selling, buying, stock, manufacturing, projects and assets. India compliance (GST) is added on the NXERP site."),
					("Sria Helpdesk", "Available", "Tickets with teams and assignment, knowledge base, service levels and a customer portal."),
					("AIRA HRMS", "Coming soon", "People records, attendance and leave, workforce reporting. Not installed on this site."),
				),
			},
			{
				"type": "steps",
				"title": "How a product joins the platform",
				"items": (
					{"title": "It is announced", "body": "Listed here and on the products page as coming soon, with no sign-up and no sign-in."},
					{"title": "It is installed and registered", "body": "Registered once, so the launcher, access rules and this site know about it."},
					{"title": "It becomes available", "body": "The announcement is replaced by the product, and people can request access."},
				),
			},
		),
		"cta": {"label": "Get in touch", "href": "/get-in-touch"},
	},
	"company": {
		"eyebrow": "Company",
		"title": "Built by Sria Infotech",
		"lead": "NXDESK is the platform layer Sria Infotech builds around the business applications it runs for teams.",
		"blocks": (
			{
				"icon": "building",
				"title": "Who builds it",
				"body": "Sria Infotech Pvt Ltd designs and maintains NXDESK, NXERP and Sria Helpdesk.",
			},
			{
				"icon": "layers",
				"title": "Open foundations",
				"body": "The applications are built on the open-source Frappe Framework and ERPNext, kept at pinned versions.",
			},
			{
				"icon": "shield",
				"title": "Careful by default",
				"body": "Access is explicit, changes are reviewed, and nothing is presented as available until it is installed.",
			},
		),
		"sections": (
			{
				"type": "story",
				"title": "About Sria Infotech",
				"paragraphs": (
					"Sria Infotech is a technology services company based in Hyderabad, India. It helps organisations make better use of technology through consulting, implementation, integration and support.",
					"NXDESK grew out of that work: a shared sign-in and launcher for the business applications a team already runs, so people open what they need from one place.",
				),
			},
			{
				"type": "steps",
				"title": "How we work with you",
				"items": (
					{"title": "We listen first", "body": "We start with what your team needs, not with a product list."},
					{"title": "We keep it clear", "body": "Plain explanations of what is installed, what it does and what it does not."},
					{"title": "We choose practical solutions", "body": "The simplest set-up that does the job, using open foundations."},
					{"title": "We stay after go-live", "body": "Support and changes as your systems and your team evolve."},
				),
			},
			{"type": "products", "title": "What runs on NXDESK today"},
			{"type": "offices", "title": "Our offices"},
		),
		"cta": {"label": "Get in touch", "href": "/get-in-touch"},
	},
	"partners": {
		"eyebrow": "Partners",
		"title": "Work with us",
		"lead": "If you implement, integrate or support business software and want to work together, tell us about your team.",
		"blocks": (
			{
				"icon": "globe",
				"title": "Implementation",
				"body": "Help organisations set up and adopt the applications on the platform.",
			},
			{
				"icon": "layers",
				"title": "Integration",
				"body": "Connect other systems to the applications through their documented interfaces.",
			},
			{
				"icon": "headset",
				"title": "Support",
				"body": "Look after the day-to-day for teams that run the platform.",
			},
		),
		"sections": (
			{
				"type": "steps",
				"title": "How a partnership starts",
				"items": (
					{"title": "Tell us about your team", "body": "What you do, which applications you work with and where you are based."},
					{"title": "We reply", "body": "Someone from Sria Infotech writes back to talk through fit and next steps."},
					{"title": "We scope it together", "body": "We agree what you will implement, integrate or support, and how we will work."},
				),
			},
			{"type": "form", "kind": "Partnership", "title": "Tell us about your team", "company": True},
		),
		"cta": {"label": "Get in touch", "href": "/get-in-touch"},
	},
	"get-in-touch": {
		"eyebrow": "Contact",
		"title": "Get in touch",
		"lead": "Questions about the platform, a product or working together? Write to us and we will reply.",
		"blocks": (),
		"sections": (
			{"type": "contact", "title": "Reach us directly"},
			{"type": "form", "kind": "General", "title": "Send us a message", "company": False},
			{"type": "offices", "title": "Our offices"},
		),
		"cta": None,
	},
}

# Navigation groups. `Products` is filled from the registry (and the announced products) at request time.
NAV_STATIC = (
	{
		"label": "Platform",
		"children": (
			{"title": "Overview", "desc": "One sign-in, access by role", "href": "/platform", "icon": "layers"},
			{"title": "Access and security", "desc": "Decided on the server", "href": "/security", "icon": "shield"},
			{"title": "Roadmap", "desc": "Available and coming soon", "href": "/roadmap", "icon": "list"},
		),
	},
	{"label": "Solutions", "href": "/solutions"},
	{
		"label": "Company",
		"children": (
			{"title": "About", "desc": "Who builds NXDESK", "href": "/company", "icon": "building"},
			{"title": "Partners", "desc": "Work with us", "href": "/partners", "icon": "handshake"},
			{"title": "Get in touch", "desc": "Write to us", "href": "/get-in-touch", "icon": "mail"},
		),
	},
)


def upcoming(installed_keys=()):
	"""Announced products that are not installed (an installed one is shown from the registry instead)."""
	return [u for u in UPCOMING if u.key not in installed_keys]


def upcoming_entry(key, installed_keys=()):
	return next((u for u in upcoming(installed_keys) if u.key == key), None)
