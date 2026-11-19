"""Database connections for the shared service, from environment variables. No frappe.

One account per role (the account matrix in docs/architecture-isolation, blueprint 2.5). A service reads only its own role's
variables, so the projector never holds the Read API's password and neither holds the root password.

	SHARED_DB_HOST (default shared-db)  SHARED_DB_PORT (3306)  SHARED_DB_NAME (nxerp_shared)
	SHARED_DB_REQUIRE_SSL=1             SHARED_DB_SSL_CA (optional CA file)
	SHARED_<ROLE>_USER, SHARED_<ROLE>_PASSWORD for ROLE in MIGRATE, PROJECTOR, READAPI; SHARED_DB_ROOT_PASSWORD for root
"""

import os
from dataclasses import dataclass

DEFAULT_USERS = {
	"migrate": "shared_migrate",
	"projector": "shared_projector",
	"readapi": "shared_readapi",
	"root": "root",
}


class SettingsError(RuntimeError):
	"""A required environment variable is missing."""


@dataclass(frozen=True)
class DbSettings:
	host: str
	port: int
	name: str
	user: str
	password: str = ""
	require_ssl: bool = False
	ssl_ca: str | None = None

	def __repr__(self) -> str:  # never print the password
		return (
			f"DbSettings(host={self.host!r}, port={self.port}, name={self.name!r}, "
			f"user={self.user!r}, password=[REDACTED])"
		)


def settings_from_env(role: str, env=None) -> DbSettings:
	"""The connection settings of one role (`migrate`, `projector`, `readapi`, `root`)."""
	env = os.environ if env is None else env
	if role not in DEFAULT_USERS:
		raise ValueError(f"unknown role {role!r}")
	if role == "root":
		password = env.get("SHARED_DB_ROOT_PASSWORD", "")
		user = "root"
	else:
		password = env.get(f"SHARED_{role.upper()}_PASSWORD", "")
		user = env.get(f"SHARED_{role.upper()}_USER", DEFAULT_USERS[role])
	if not password:
		raise SettingsError(f"the password for the {role} account is not set in the environment")
	return DbSettings(
		host=env.get("SHARED_DB_HOST", "shared-db"),
		port=int(env.get("SHARED_DB_PORT", "3306")),
		name=env.get("SHARED_DB_NAME", "nxerp_shared"),
		user=user,
		password=password,
		require_ssl=env.get("SHARED_DB_REQUIRE_SSL", "0") == "1",
		ssl_ca=env.get("SHARED_DB_SSL_CA") or None,
	)


def connect(settings: DbSettings, database: str | None = "default", autocommit: bool = False):
	"""A PyMySQL connection (utf8mb4, short connect timeout, dict rows). `database=None` selects no database."""
	import pymysql
	import pymysql.cursors

	kwargs = {
		"host": settings.host,
		"port": settings.port,
		"user": settings.user,
		"password": settings.password,
		"charset": "utf8mb4",
		"autocommit": autocommit,
		"connect_timeout": 5,
		"read_timeout": 30,
		"write_timeout": 30,
		"cursorclass": pymysql.cursors.DictCursor,
	}
	if database == "default":
		kwargs["database"] = settings.name
	elif database:
		kwargs["database"] = database
	if settings.require_ssl:
		kwargs["ssl"] = {"ca": settings.ssl_ca} if settings.ssl_ca else {"check_hostname": False}
		if not settings.ssl_ca:
			kwargs["ssl_verify_cert"] = False
	return pymysql.connect(**kwargs)
