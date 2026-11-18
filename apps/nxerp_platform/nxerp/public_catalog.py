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
}

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
		"cta": {"label": "Get in touch", "href": "/get-in-touch"},
	},
	"get-in-touch": {
		"eyebrow": "Contact",
		"title": "Get in touch",
		"lead": "Questions about the platform, a product or working together? Write to us and we will reply.",
		"blocks": (),
		"cta": None,
	},
}

# Navigation groups. `Products` is filled from the registry (and the announced products) at request time.
NAV_STATIC = (
	{
		"label": "Platform",
		"children": (
			{"title": "Overview", "desc": "One sign-in, access by role", "href": "/platform"},
			{"title": "Access and security", "desc": "Decided on the server", "href": "/security"},
			{"title": "Roadmap", "desc": "Available and coming soon", "href": "/roadmap"},
		),
	},
	{"label": "Solutions", "href": "/solutions"},
	{
		"label": "Company",
		"children": (
			{"title": "About", "desc": "Who builds NXDESK", "href": "/company"},
			{"title": "Partners", "desc": "Work with us", "href": "/partners"},
			{"title": "Get in touch", "desc": "Write to us", "href": "/get-in-touch"},
		),
	},
)


def upcoming(installed_keys=()):
	"""Announced products that are not installed (an installed one is shown from the registry instead)."""
	return [u for u in UPCOMING if u.key not in installed_keys]


def upcoming_entry(key, installed_keys=()):
	return next((u for u in upcoming(installed_keys) if u.key == key), None)
