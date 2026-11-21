"""Open self-signup on an existing site (Website Settings `disable_signup` = 0), once. Idempotent (see install.open_signup)."""

from nxerp.install import open_signup


def execute():
	open_signup()
