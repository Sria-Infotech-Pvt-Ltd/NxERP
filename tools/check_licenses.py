"""Check dependency licences against .github/license-policy/. Stdlib only.

	python3 -I tools/check_licenses.py pypi build/deps/requirements.txt     # name==version lines; queries pypi.org
	pip-licenses --format=json --from=mixed > py.json                       # alternative: an installed environment
	python3 -I tools/check_licenses.py pip py.json

	license-checker-rseidelsohn --production --json > js.json
	python3 -I tools/check_licenses.py npm js.json

Exit 1 when a package has a licence outside allowed-licenses.txt (and no reviewed exception) or no determinable licence.
"""

import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

POLICY = Path(__file__).resolve().parent.parent / ".github" / "license-policy"

# what the tools print -> SPDX id (lowercase keys). Trove classifiers come from pip-licenses.
ALIASES = {
	"mit license": "MIT",
	"mit": "MIT",
	"expat": "MIT",
	"bsd": "BSD-3-Clause",
	"bsd license": "BSD-3-Clause",
	"new bsd license": "BSD-3-Clause",
	"simplified bsd": "BSD-2-Clause",
	"bsd-2-clause": "BSD-2-Clause",
	"bsd-3-clause": "BSD-3-Clause",
	"apache software license": "Apache-2.0",
	"apache 2.0": "Apache-2.0",
	"apache license 2.0": "Apache-2.0",
	"apache-2.0": "Apache-2.0",
	"isc license (iscl)": "ISC",
	"isc license": "ISC",
	"python software foundation license": "PSF-2.0",
	"psf-2.0": "PSF-2.0",
	"mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
	"mpl-2.0": "MPL-2.0",
	"gnu lesser general public license v3 (lgplv3)": "LGPL-3.0",
	"gnu lesser general public license v2 or later (lgplv2+)": "LGPL-2.1",
	"the unlicense (unlicense)": "Unlicense",
	"unlicense": "Unlicense",
	"cc0-1.0": "CC0-1.0",
	"public domain": "Unlicense",
	"3-clause bsd license": "BSD-3-Clause",
	"bsd 3-clause": "BSD-3-Clause",
	"bsd 2-clause": "BSD-2-Clause",
	"2-clause bsd license": "BSD-2-Clause",
	"zope public license": "ZPL-2.1",
	"zpl-2.1": "ZPL-2.1",
	"mozilla public license 1.1 (mpl 1.1)": "MPL-1.1",
	"gnu lesser general public license v2 (lgplv2)": "LGPL-2.0",
	"gnu library or lesser general public license (lgpl)": "LGPL-2.1",
	"gnu lesser general public license v3 or later (lgplv3+)": "LGPL-3.0",
	"lgpl-2.1-or-later": "LGPL-2.1",
	"lgpl-3.0-or-later": "LGPL-3.0",
	"mit-cmu": "MIT-CMU",
}


def load_allowed():
	lines = (POLICY / "allowed-licenses.txt").read_text(encoding="utf-8").splitlines()
	return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def load_exceptions(ecosystem):
	"""package -> True when the exception is still PENDING review (passes, but is reported loudly on every run)."""
	found = {}
	for line in (POLICY / "exceptions.txt").read_text(encoding="utf-8").splitlines():
		if line.strip() and not line.startswith("#") and "|" in line:
			fields = [field.strip() for field in line.split("|")]
			key = fields[0].lower()
			if key.startswith(ecosystem + ":"):
				found[key.split(":", 1)[1]] = len(fields) < 4 or fields[3].upper().startswith("PENDING")
	return found


def normalise(token):
	token = token.strip()
	if (
		token.startswith("(") and token.endswith(")") and token.count("(") == 1
	):  # `(MIT)` but not `... (MPL 2.0)`
		token = token[1:-1].strip()
	return ALIASES.get(token.lower(), token)


def acceptable(expression, allowed):
	"""True when the licence expression is allowed. Understands SPDX expressions (`A AND (B OR C)`, `A WITH exception`) and
	trove-classifier strings; `;` and a bare `/` between classifiers are read as OR (multiple classifiers normally mean a
	dual licence, which is lenient for the rare package that means AND). Undeterminable licences are never acceptable."""
	expression = (expression or "").strip()
	if not expression or expression.upper().startswith(("UNKNOWN", "UNLICENSED", "NONE")):
		return False
	if (
		normalise(expression) in allowed
	):  # a whole classifier name such as "Mozilla Public License 2.0 (MPL 2.0)"
		return True
	if ";" in expression:
		return any(acceptable(part, allowed) for part in expression.split(";"))
	tokens = re.findall(r"[()]|[^\s()]+", expression)
	position = 0

	def peek():
		return tokens[position].upper() if position < len(tokens) else None

	def atom():
		nonlocal position
		if peek() == "(":
			position += 1
			value = either()
			if peek() == ")":
				position += 1
			return value
		words = []  # a licence name may have spaces ("BSD 3-Clause"): take words up to the next operator
		while position < len(tokens) and peek() not in {"AND", "OR", "WITH", "(", ")"}:
			words.append(tokens[position])
			position += 1
		word = " ".join(words)
		if peek() == "WITH":  # licence exception: the base licence decides
			position += 2
		return normalise(word) in allowed

	def both():
		nonlocal position
		value = atom()
		while peek() == "AND":
			position += 1
			value = atom() and value
		return value

	def either():
		nonlocal position
		value = both()
		while peek() == "OR":
			position += 1
			value = both() or value
		return value

	return either() and position >= len(tokens)


def pypi_license(name, version):
	"""Licence of one release from PyPI's JSON API: PEP 639 expression, else trove classifiers, else a short `license` field."""
	url = f"https://pypi.org/pypi/{name}/{version}/json"
	error = None
	for attempt in range(4):
		try:
			with urllib.request.urlopen(url, timeout=30) as response:
				info = json.load(response)["info"]
			break
		except (
			Exception
		) as exc:  # retry transient failures; a persistent one is reported, never treated as allowed
			error = exc
			time.sleep(2 * (attempt + 1))
	else:
		return f"UNKNOWN (lookup failed: {error})"
	if info.get("license_expression"):
		return info["license_expression"]
	classifiers = [c.rsplit(" :: ", 1)[-1] for c in info.get("classifiers", []) if c.startswith("License ::")]
	classifiers = [c for c in classifiers if c != "OSI Approved"]
	if classifiers:
		return "; ".join(classifiers)
	text = (info.get("license") or "").strip()
	return text if text and len(text) <= 80 else "UNKNOWN"


def rows(ecosystem, data):
	if ecosystem == "pypi":  # requirements.txt lines name==version
		pins = [
			line.strip().split("==", 1)
			for line in data.splitlines()
			if "==" in line and not line.startswith("#")
		]
		with ThreadPoolExecutor(max_workers=8) as pool:
			licenses = list(pool.map(lambda pin: pypi_license(*pin), pins))
		for (name, version), expression in zip(pins, licenses, strict=True):
			yield name, version, expression
	elif ecosystem == "pip":  # pip-licenses JSON: [{"Name", "Version", "License"}]
		for item in data:
			yield item["Name"], item["Version"], item["License"]
	else:  # license-checker JSON: {"name@version": {"licenses": "MIT"}}
		for key, item in data.items():
			name, _, version = key.rpartition("@")
			licenses = item.get("licenses", "UNKNOWN")
			yield name, version, " OR ".join(licenses) if isinstance(licenses, list) else licenses


def main(argv):
	if len(argv) != 3 or argv[1] not in {"pip", "npm", "pypi"}:
		print(__doc__)
		return 2
	ecosystem, path = argv[1], argv[2]
	allowed, exceptions = load_allowed(), load_exceptions("pip" if ecosystem == "pypi" else ecosystem)
	text = Path(path).read_text(encoding="utf-8")
	data = text if ecosystem == "pypi" else json.loads(text)
	bad, pending = [], []
	total = 0
	for name, version, expression in rows(ecosystem, data):
		total += 1
		if name.lower() in exceptions:
			if exceptions[name.lower()]:
				pending.append(f"{name}=={version}: {expression or 'UNKNOWN'}")
			continue
		if acceptable(expression, allowed):
			continue
		bad.append(f"{name}=={version}: {expression or 'UNKNOWN'}")
	print(f"{ecosystem}: {total} packages checked, {len(bad)} outside the licence policy")
	for line in bad:
		print(f"  NOT ALLOWED  {line}")
	for line in pending:
		print(f"  PENDING REVIEW (passes only because exceptions.txt lists it as pending)  {line}")
	return 1 if bad else 0


if __name__ == "__main__":
	sys.exit(main(sys.argv))
