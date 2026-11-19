"""Sources: which owner feeds the projector reads. No frappe.

The sources file (JSON, `SHARED_SOURCES_FILE`, default /etc/nxerp-shared/sources.json) lists one entry per feed:

	{"sources": [{"app_key": "nxerp", "base_url": "https://nxerp.example.test",
	              "key_file": "/run/nxerp-shared/feed-nxerp.key", "host_header": null}]}

`app_key` names the feed and is the key of its cursor (in a single-site development stack one feed can carry the events of
several owner apps). `key_file` holds one line, `api_key:api_secret`, of the owner's feed service user; the file lives outside the
repository and its content is never logged. `host_header` selects the site when the URL is a shared address (the owner's web
server picks the site from the Host header). `http://` URLs are refused unless SHARED_ALLOW_INSECURE_FEED=1, which is for a
throwaway test stack only.
"""

import json
import os
import re
from dataclasses import dataclass

DEFAULT_SOURCES_FILE = "/etc/nxerp-shared/sources.json"
APP_KEY = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")
KEY_LINE = re.compile(r"^[A-Za-z0-9_\-]{4,64}:[A-Za-z0-9_\-]{4,64}$")


class ConfigError(ValueError):
	"""The sources file or a key file is not usable."""


@dataclass(frozen=True)
class Source:
	app_key: str
	base_url: str
	key_file: str
	host_header: str | None = None


def insecure_allowed(env=None) -> bool:
	env = os.environ if env is None else env
	return env.get("SHARED_ALLOW_INSECURE_FEED", "0") == "1"


def parse_sources(data: dict, env=None) -> list:
	"""Validate the parsed JSON and return the sources."""
	if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
		raise ConfigError('the sources file must be {"sources": [...]}')
	sources, seen = [], set()
	for index, entry in enumerate(data["sources"]):
		if not isinstance(entry, dict):
			raise ConfigError(f"sources[{index}] must be an object")
		unknown = set(entry) - {"app_key", "base_url", "key_file", "host_header"}
		if unknown:
			raise ConfigError(f"sources[{index}] has unknown keys {sorted(unknown)}")
		app_key, base_url, key_file = entry.get("app_key"), entry.get("base_url"), entry.get("key_file")
		if not isinstance(app_key, str) or not APP_KEY.fullmatch(app_key):
			raise ConfigError(f"sources[{index}].app_key must match {APP_KEY.pattern}")
		if app_key in seen:
			raise ConfigError(f"duplicate app_key {app_key}")
		seen.add(app_key)
		if not isinstance(base_url, str) or not re.match(r"^https?://[^/\s]+/?$", base_url):
			raise ConfigError(f"sources[{index}].base_url must be http(s)://host[:port] with no path")
		if base_url.startswith("http://") and not insecure_allowed(env):
			raise ConfigError(
				f"sources[{index}].base_url is http://: feeds are https only (SHARED_ALLOW_INSECURE_FEED=1 is for a throwaway test stack)"
			)
		if not isinstance(key_file, str) or not key_file:
			raise ConfigError(f"sources[{index}].key_file is required")
		host_header = entry.get("host_header")
		if host_header is not None and (
			not isinstance(host_header, str) or not re.fullmatch(r"[A-Za-z0-9.\-:]{1,255}", host_header)
		):
			raise ConfigError(f"sources[{index}].host_header is not a host name")
		sources.append(Source(app_key, base_url.rstrip("/"), key_file, host_header))
	return sources


def load_sources(path: str | None = None, env=None) -> list:
	env = os.environ if env is None else env
	path = path or env.get("SHARED_SOURCES_FILE", DEFAULT_SOURCES_FILE)
	try:
		with open(path, encoding="utf-8") as handle:
			data = json.load(handle)
	except (OSError, ValueError) as exc:
		raise ConfigError(f"cannot read the sources file {path}: {type(exc).__name__}") from exc
	return parse_sources(data, env)


def read_key(source: Source) -> str:
	"""The `api_key:api_secret` of a source, read from its key file. Never logged."""
	try:
		with open(source.key_file, encoding="utf-8") as handle:
			line = handle.readline().strip()
	except OSError as exc:
		raise ConfigError(f"cannot read the key file of {source.app_key}: {type(exc).__name__}") from exc
	if not KEY_LINE.fullmatch(line):
		raise ConfigError(f"the key file of {source.app_key} must hold one line, api_key:api_secret")
	return line
