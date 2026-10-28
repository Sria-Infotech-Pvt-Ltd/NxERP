# nxerp_platform (Frappe app `nxerp`)

The NXERP platform app: the shared login (`/login`), the post-login router (`/nxerp/go`), the launcher (`/nxerp/apps`),
the access layer that decides which apps a user may enter (enforced on the server), and platform branding.

- **Folder name vs app name.** This folder is `apps/nxerp_platform/`; the Frappe app and Python package are called
  **`nxerp`** (`nxerp/hooks.py`, `pyproject.toml`). The package name is part of the installed-app record, the patch log,
  the `/assets/nxerp/...` and `/nxerp/...` URLs and every dotted path in `hooks.py`, so it must not be renamed.
  The folder `nxerp/nxerp_platform/` is the Frappe *module* ("NXERP Platform") listed in `modules.txt`.
- **Layout:** `nxerp/` the package (flat modules: `access`, `enforcement`, `guard`, `routing`, `launcher`, `registry`,
  `audit`, `install`, `migration`; plus `api/`, `patches/`, `public/`, `www/`, `tests/`), `browser-tests/` the Chromium
  suite for login, router and launcher (see its README), `pyproject.toml`.
- **Where each function lives:** `docs/architecture/code-map.md`. **Rules:** `docs/architecture/rules.md`.
- This app never imports another app; only its registry (`nxerp/registry.py`) knows which apps exist.
