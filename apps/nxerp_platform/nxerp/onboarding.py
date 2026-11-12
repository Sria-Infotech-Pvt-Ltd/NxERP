"""First-run onboarding for one product: the questions, the saved answers, and what "submit" does under the product's
signup policy (D3). Every function takes the user as an argument and the API layer passes `frappe.session.user`,
never a request parameter, so one user can only ever touch their own state.

Self-signup never grants staff access: the most this module grants is a product's PORTAL role, and only under
`open_portal`. Everything else creates an access request that an administrator decides.

Answers are never logged. They live in `NXERP Onboarding.answers` and in two User fields (language, time zone).
"""

import json
from zoneinfo import available_timezones

import frappe
from frappe import _
from frappe.utils import now_datetime

from nxerp import access, audit, registry

REQUEST_STEP = "request"

CHOICES = {
	"kind_of_work": (
		("finance", "Finance and accounting"),
		("sales", "Sales and purchasing"),
		("operations", "Operations and stock"),
		("support", "Customer support"),
		("other", "Something else"),
	),
	"team_size": (
		("1", "Just me"),
		("2-10", "2 to 10 people"),
		("11-50", "11 to 50 people"),
		("50+", "More than 50"),
	),
}

# step -> the fields it accepts; `optional` steps may be skipped with an empty answer
STEPS = {
	"basics": {"fields": ("language", "time_zone"), "optional": False},
	"about": {"fields": ("kind_of_work", "team_size"), "optional": True},
}
MAX_VALUE_LENGTH = 100


def steps_for(entry) -> list:
	"""The registry's onboarding steps that exist, then the final `request` step."""
	return [s for s in entry.onboarding_steps if s in STEPS] + [REQUEST_STEP]


def _entry(app_key):
	entry = registry.get_entry(app_key) if isinstance(app_key, str) else None
	if not entry:
		frappe.throw(_("Unknown or uninstalled application"), frappe.DoesNotExistError)
	return entry


def _doc(user: str, app_key: str, create: bool = False):
	name = f"{user}:{app_key}"
	if frappe.db.exists("NXERP Onboarding", name):
		return frappe.get_doc("NXERP Onboarding", name)
	if not create:
		return None
	return frappe.get_doc({"doctype": "NXERP Onboarding", "user": user, "app_key": app_key, "answers": "{}"})


def _persist(doc):
	doc.flags.ignore_permissions = True
	if doc.is_new():
		doc.insert()
	else:
		doc.save()


def _answers(doc) -> dict:
	try:
		value = json.loads(doc.answers) if doc and doc.answers else {}
	except ValueError:
		return {}
	return value if isinstance(value, dict) else {}


def open_request(user: str, app_key: str):
	return frappe.db.get_value(
		"NXERP Access Request", {"user": user, "app_key": app_key, "status": "Pending"}, "name"
	)


def _languages() -> list:
	names = frappe.get_all("Language", filters={"enabled": 1}, pluck="name", order_by="name") or ["en"]
	return names if "en" in names else ["en", *names]


def options() -> dict:
	"""Choices for the wizard's selects: enabled languages, time zones, and the two multiple-choice questions."""
	return {
		"languages": [
			{"value": code, "label": frappe.db.get_value("Language", code, "language_name") or code}
			for code in _languages()
		],
		"time_zones": sorted(t for t in available_timezones() if "/" in t or t == "UTC"),
		"kind_of_work": [{"value": v, "label": _(label)} for v, label in CHOICES["kind_of_work"]],
		"team_size": [{"value": v, "label": _(label)} for v, label in CHOICES["team_size"]],
	}


def get_state(user: str, app_key: str) -> dict:
	entry = _entry(app_key)
	steps = steps_for(entry)
	doc = _doc(user, app_key)
	answers = _answers(doc)
	done = [s for s in steps if s != REQUEST_STEP and s in answers]

	if access.can_access_app(user, app_key):
		status = "granted"
	elif open_request(user, app_key):
		status = "pending"
	elif doc and doc.completed_on and entry.signup_policy == "invite_only":
		status = "invitation"
	elif (
		doc
		and doc.completed_on
		and entry.signup_policy == "open_portal"
		and access.can_use_portal(user, app_key)
	):
		status = "granted"
	else:
		status = "wizard"

	current = next((s for s in steps if s not in done and s != REQUEST_STEP), REQUEST_STEP)
	saved = frappe.db.get_value("User", user, ["language", "time_zone"], as_dict=True) or {}
	values = {
		"language": saved.get("language") or "en",
		"time_zone": saved.get("time_zone") or frappe.utils.get_system_timezone(),
	}
	for step in done:
		values.update({k: v for k, v in (answers.get(step) or {}).items() if k in STEPS[step]["fields"]})
	return {
		"app": entry.key,
		"title": entry.public_title,
		"policy": entry.signup_policy,
		"steps": steps,
		"done": done,
		"current": current,
		"status": status,
		"route": entry.route if status == "granted" else None,
		"values": values,
	}


def _clean(step: str, data) -> dict:
	spec = STEPS[step]
	if not isinstance(data, dict) or set(data) - set(spec["fields"]):
		frappe.throw(_("Invalid answers"), frappe.ValidationError)
	clean = {}
	for field in spec["fields"]:
		value = data.get(field)
		if value in (None, ""):
			clean[field] = ""
			continue
		if not isinstance(value, str) or len(value) > MAX_VALUE_LENGTH:
			frappe.throw(_("Invalid answers"), frappe.ValidationError)
		clean[field] = value
	if step == "basics":
		if clean["language"] not in _languages():
			frappe.throw(_("Choose a language from the list"), frappe.ValidationError)
		if clean["time_zone"] not in available_timezones():
			frappe.throw(_("Choose a time zone from the list"), frappe.ValidationError)
	else:
		for field in ("kind_of_work", "team_size"):
			if clean.get(field) and clean[field] not in {v for v, _label in CHOICES[field]}:
				frappe.throw(_("Choose one of the listed answers"), frappe.ValidationError)
	if not spec["optional"] and not all(clean.values()):
		frappe.throw(_("Please answer every question on this step"), frappe.ValidationError)
	return clean


def save_step(user: str, app_key: str, step: str, data) -> dict:
	entry = _entry(app_key)
	if step not in steps_for(entry) or step == REQUEST_STEP:
		frappe.throw(_("Unknown step"), frappe.ValidationError)
	if get_state(user, app_key)["status"] != "wizard":
		frappe.throw(_("This request is already submitted"), frappe.ValidationError)
	clean = _clean(step, data)

	if step == "basics":
		frappe.db.set_value("User", user, {"language": clean["language"], "time_zone": clean["time_zone"]})
		frappe.clear_cache(user=user)

	doc = _doc(user, app_key, create=True)
	answers = _answers(doc)
	answers[step] = clean
	doc.answers = json.dumps(answers)
	doc.step = step
	_persist(doc)
	return get_state(user, app_key)


def submit(user: str, app_key: str) -> dict:
	"""Finish the wizard under the product's policy. Idempotent: a second call changes nothing."""
	entry = _entry(app_key)
	state = get_state(user, app_key)
	if state["status"] != "wizard":
		return state
	required = [s for s in steps_for(entry) if s != REQUEST_STEP and not STEPS[s]["optional"]]
	if not all(s in state["done"] for s in required):
		frappe.throw(_("Please finish the earlier steps first"), frappe.ValidationError)

	doc = _doc(user, app_key, create=True)
	doc.completed_on = now_datetime()
	_persist(doc)

	policy = entry.signup_policy
	if policy == "open_portal" and entry.portal_roles:
		user_doc = frappe.get_doc("User", user)
		if entry.portal_roles[0] not in {r.role for r in user_doc.roles}:
			user_doc.append("roles", {"role": entry.portal_roles[0]})  # a portal role, never a staff role
			user_doc.flags.ignore_permissions = True
			user_doc.save()
		audit.log_event("portal_granted", entry.key, user)
	elif policy != "invite_only":
		create_request(user, entry)
	return get_state(user, app_key)


def create_request(user: str, entry):
	req = frappe.get_doc(
		{"doctype": "NXERP Access Request", "user": user, "app_key": entry.key, "status": "Pending"}
	)
	req.flags.ignore_permissions = True
	req.insert()
	audit.log_event("requested", entry.key, user)
	notify_administrators(req, entry)
	return req


def administrators() -> list:
	names = frappe.get_all(
		"Has Role", filters={"role": "System Manager", "parenttype": "User"}, pluck="parent"
	)
	users = frappe.get_all(
		"User",
		filters={"name": ["in", names or [""]], "enabled": 1, "user_type": "System User"},
		fields=["name", "email"],
	)
	return [u.email for u in users if u.email and u.name not in ("Administrator", "Guest")]


def notify_administrators(req, entry):
	recipients = administrators()
	if not recipients:
		return
	who = frappe.utils.escape_html(frappe.utils.get_fullname(req.user))
	title = frappe.utils.escape_html(entry.public_title)
	try:
		frappe.sendmail(
			recipients=recipients,
			subject=_("Access request for {0}").format(entry.public_title),
			message=_("{0} asked for access to {1}. Review it in the access request queue: {2}").format(
				who, title, frappe.utils.get_url("/desk/nxerp-access-request")
			),
			reference_doctype=req.doctype,
			reference_name=req.name,
		)
	except frappe.OutgoingEmailError:
		pass  # the request exists and is in the queue; a mail failure must not undo it
