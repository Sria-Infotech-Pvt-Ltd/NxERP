"""Enable self-signup only when site config `nxerp_enable_signup` is 1. Idempotent (see install.sync_signup_setting)."""

from nxerp.install import sync_signup_setting


def execute():
	sync_signup_setting()
