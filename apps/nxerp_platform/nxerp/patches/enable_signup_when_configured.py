"""Historical: this patch opened signup only when site config `nxerp_enable_signup` was 1. That switch is gone; it now just opens signup, like
`open_signup_for_everyone`. It has already run on existing sites. Idempotent (see install.open_signup)."""

from nxerp.install import open_signup


def execute():
	open_signup()
