# NXERP

Branding and the NXERP sign-in page for the site.

## What it does

- Replaces the `/login` page with the NXERP design (`nxerp/www/login.html` + `login.py` + `public/css/nxerp-login.css`).
- The sign-in logic is **not** re-implemented: the page extends the platform's own login page, so the form fields, `login.js`,
  forgot password, email-link login, 2FA, social login and `redirect-to` behave exactly as before. Only layout and styling change.
- Sets the NXERP name/logo (`nxerp/branding.py`).

## Install (existing bench)

```bash
bench get-app /path/to/NXERP/nxerp        # or copy the folder into apps/ and: pip install -e apps/nxerp
bench --site <site> install-app nxerp     # install AFTER the other apps (the last-installed app wins for /login)
bench --site <site> execute nxerp.branding.apply_branding   # only needed on an already-existing site
bench --site <site> clear-cache
bench restart
```

Uninstall = `bench --site <site> uninstall-app nxerp` and the stock login page returns.

## Images

`nxerp/public/images/` holds the NXERP wordmarks, mark, favicon, and hero backgrounds; `nxerp/public/fonts/` holds the self-hosted login fonts.
Replace the files (same names) to change them.
