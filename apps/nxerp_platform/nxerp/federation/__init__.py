"""Login federation (ADR-003 amendment 2, Phase 6): the identity site copies access grants to the app sites.

Everything here is off unless the site config key `nxerp_site_role` is set (identity: sends, app: receives).
No password ever leaves the identity site: an app-site user is created without one and signs in through the identity site.
"""
