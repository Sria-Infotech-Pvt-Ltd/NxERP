# ADR-006: Development environment and one-command bootstrap

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

Developers use Windows machines (this workstation: Windows 11, Docker Desktop 29.6.1, Compose v5.1.4). Frappe needs Python 3.14, Node 24, MariaDB and Redis.

**FACT** (tooling check on the workstation): `docker` and `docker compose` present; `bench` **not found**; Python 3.14.3 and Node 24.18 are installed on the host but bench/Frappe are not supported natively on Windows (no bench, no MariaDB/Redis services). Docker Desktop is allotted 8 GB RAM and the system drive had 23 GB free, so images and volumes must stay lean.

## Options

| Option | Verdict |
| --- | --- |
| Native bench on the host | Rejected: not available on Windows; every developer would hand-build Python 3.14, Node 24, MariaDB, Redis |
| VS Code devcontainer (frappe_docker `devcontainer-example`) | Possible later (a thin `devcontainer.json` over the same compose file); not required for the one-command goal |
| **Docker Compose dev stack in `deploy/dev/` (chosen)** | Works on Windows/macOS/Linux, versions pinned by digest, no host toolchain |
| WSL2 native bench | Rejected as the baseline: per-developer setup drift |

## Decision

- `./deploy/dev/up.sh -d` is the one command. It creates `deploy/dev/.env` (random passwords, git-ignored), then `docker compose up`. The `bench` service runs `deploy/dev/bootstrap.sh`: bench init (Frappe pinned and commit-verified), each app in `deploy/apps.json` fetched at its pinned commit and cloned into `apps/`, one `bench build`, `new-site`, `install-app` in order, then `bench start`. It is idempotent.
- The bench lives in a named volume (fast, outside OneDrive-synced folders); the repo is bind-mounted at `/workspace` and `nxerp` is soft-linked from it, so edits apply live.
- Host ports 8100 (web) and 9100 (realtime) and compose project `nxerp-dev` avoid clashes with the legacy `frappe-helpdesk-docker` stack, which is left untouched.
- Repositories should be cloned **outside OneDrive** (a partial `.git` lock was observed when renaming a clone inside a synced folder).
- Dev-only conveniences (`developer_mode`, `mute_emails`, fake-user seeding) are guarded and never enabled by production tooling.

## Consequences

- First run downloads and builds for a long time; see `docs/audit/bootstrap-evidence.md` for the measured duration.
- Production images (frappe_docker layered image consuming `deploy/apps.json`) are a follow-up and are **not** claimed to work.
