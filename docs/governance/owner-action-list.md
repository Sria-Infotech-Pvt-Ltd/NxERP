# Owner action list

Everything below needs a human with rights this work did not have (GitHub admin, a host, a registry, DNS, SMTP, cloud storage).
**Every item is "ready, not executed".** The repository contains the templates, scripts and workflows for each; none has been run
against the real service. Do them in this order; later items depend on earlier ones. Tick the box only after you have seen the result,
and note what you saw.

## A. Get the code onto GitHub and make CI run

1. [ ] **Grant write access** to the person/automation that pushes (the account used so far, `rohanaarup`, has `READ` only on
   `Sria-Infotech-Pvt-Ltd/NxERP`), or push from an account that has it. *Ready, not executed.*
2. [ ] **Push the local branches** (nothing has been pushed; verify afterwards with `git ls-remote origin`): `phase-1/foundation`,
   `phase-2/access-layer`, `phase-3/unified-experience`, `phase-4/release-readiness`. Open PRs in that order (each branch is cut from
   the previous one). Decide the commit author first (`docs/PROGRESS.md`, open item 2). *Ready, not executed.*
3. [ ] **Push the Helpdesk fork work and re-pin it.** `deploy/apps.json` pins Helpdesk to `1c6981cc5`, an interim commit of
   `Sriainfotech/Frappe-Help-Desk`; the branches that Phases 2-3 need (`feature/nxerp-platform-login`, the palette branch) exist only
   locally. Push them, then update the `helpdesk` pin in `deploy/apps.json` to a commit that exists on the remote, update ADR-002 and
   run `python3 -I deploy/check_pins.py`. **Until then CI cannot build a stack that has the platform login, and the nxerp tests that
   depend on it will fail on GitHub.** Also decide the fork's home (`Sriainfotech` vs the company org). *Ready, not executed.*
4. [ ] **Create the read token for the Helpdesk fork** (needed only if the fork is private): a fine-grained token or deploy key with
   read-only access to that one repository; store it as repository secret `HELPDESK_READ_TOKEN`. Used by every job that checks Helpdesk
   out and by the image build (BuildKit secret). *Ready, not executed.*
5. [ ] **Read the first CI run** (`.github/workflows/ci.yml`). It has never run on GitHub; expect to fix workflow problems. Check in
   particular: the stack-cache restore (`tools/ci_stack.sh volumes restore`), the e2e shards, the volume cache and runner disk (see "Risks" in
   `docs/governance/ci-design.md`), and runner disk space. *Not executed.*

## B. Teams, protection, settings (needs organisation/repository admin)

6. [ ] **Create the GitHub teams** named in `CODEOWNERS`: `nxerp-platform`, `nxerp-security`, `nxerp-devops`, `nxerp-architecture`,
   `nxerp-maintainers` (or replace the names by real users/teams) and give them Write access. Until they exist CODEOWNERS enforces
   nothing. *Ready, not executed.*
7. [ ] **Apply branch protection**: dry-run `docs/governance/apply-branch-protection.sh`, then `--apply` as an admin (required check
   `ci-gate`, review count, code owners, linear history, admins included, squash-only, auto-delete branches), or follow the UI
   click-paths in `docs/governance/branch-protection.md`. `ci-gate` must have reported once first. *Ready, not executed.*
8. [ ] **Enable security features** in Settings > Code security: Dependabot alerts and security updates, secret scanning + push
   protection, and **code scanning**. Private repositories need **GitHub Advanced Security** for CodeQL; without it set repository
   variable `CODEQL_ENABLED=false` (the `codeql` job then skips and `ci-gate` accepts that, for that job only).
   `.github/dependabot.yml` does nothing until Dependabot is enabled. *Ready, not executed.*
9. [ ] **Triage the dependency advisories** `dependency-audit` reports. FACT: pip-audit run locally on 2026-10-28 against Frappe's own
   resolved dependencies found 59 advisories in 5 packages (pillow 38, pypdf 11, gitpython 6, filelock 2, pdfkit 2); Frappe does not lock
   its Python dependencies, so a fresh image build installs whatever is newest. Decide: constrain/pin (a constraints file for the image
   build), accept with a dated reason, or wait for Frappe. Then set repository variable `AUDIT_ENFORCE=true` so the job blocks. *Ready,
   not executed.*
10. [ ] **Licence decisions.** (a) Choose the licence for `nxerp` (`hooks.py` says `Proprietary` as a placeholder). (b) Have counsel review
    what shipping ERPNext (GPL-3.0), Helpdesk (AGPL-3.0) and `mysqlclient` (GPL-2.0+) together with a proprietary app means for
    distribution/hosting; this is a legal question this repository does not settle. (c) Review the two `PENDING` entries in
    `.github/license-policy/exceptions.txt` (`mysqlclient`, `typst`). *Ready, not executed.*

## C. Registry, hosts, domains, secrets

11. [ ] **Container registry.** The workflows assume GHCR (`ghcr.io/sria-infotech-pvt-ltd/nxerp`, override with variable
    `NXERP_IMAGE`). Confirm GHCR is acceptable (private package, organisation visibility), create a read-only pull token for the hosts
    (`REGISTRY_PULL_TOKEN`). *Ready, not executed.*
12. [ ] **Staging host** and **production host**: Docker + Compose v2, a `deploy` user, the directory from
    `deploy/environments/README.md`, firewall (only 443/22), time sync, disk for backups. *Ready, not executed.*
13. [ ] **Domains and TLS**: DNS names for staging and production, certificates, a TLS-terminating reverse proxy/load balancer in front of
    the compose `proxy` service (it speaks HTTP only), HSTS decision. *Ready, not executed.*
14. [ ] **Deploy credentials**: an SSH key pair per environment (public key on the host's `deploy` user; private key as environment
    secret `DEPLOY_SSH_KEY`), `DEPLOY_KNOWN_HOSTS` from `ssh-keyscan`, restricted to the deploy directory. *Ready, not executed.*
15. [ ] **GitHub Environments** `staging` and `production` with their variables (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_PATH`,
    `NXERP_SITE`, `STAGING_URL`/`PRODUCTION_URL`, `NXERP_BACKUP_DIR`) and secrets (see `deploy/environments/*.env.example`). **`production`
    needs required reviewers and "prevent self-review" BEFORE any production secret is stored in it** (an Environment without reviewers
    deploys without approval). *Ready, not executed.*
16. [ ] **Host secrets**: create `/opt/nxerp/.env` (mode 600) on each host with generated database root/admin passwords and
    `NXERP_IMAGE_TAG` (`deploy/staging-like/.env.example`). The CI system never holds these. *Ready, not executed.*
17. [ ] **SMTP**: an outgoing mail account for each environment, configured as the site's default Email Account (staging should use a sink
    or a restricted domain, so test mail never reaches real people). The platform's mails are still titled "Login To Frappe" (branding
    not done). *Ready, not executed.*
18. [ ] **Backup storage**: off-host, encrypted, access-controlled storage and a command for `NXERP_BACKUP_UPLOAD_CMD`; retention
    (`NXERP_BACKUP_KEEP_DAYS`); a schedule (cron/systemd timer running `deploy/scripts/backup.sh`); a restore drill on a scratch host,
    written down in `docs/runbooks/backup-restore.md` with the date. Backups contain personal data and the site `encryption_key`.
    *Ready, not executed.*

## D. First release

19. [ ] **Build the image once for real** on a machine with disk and network (`deploy/docker/build.sh`): only `docker buildx build --check`
    passed so far; the build itself, its size, the SBOM and a `docker compose up` of `deploy/staging-like/` have NOT run. Fix what breaks.
20. [ ] **First release candidate**: bump `__version__`, merge, tag `vX.Y.Z-rc.1` on `main` after `ci-gate` is green, watch `release.yml`
    then `deploy-staging.yml`, run the restore drill and the rollback drill on staging, then promote with `deploy-production.yml`.
    Follow `docs/runbooks/release.md`. The `upgrade-from-previous-tag` job only starts testing after the first stable tag exists.
21. [ ] **Decide the staging journey tests.** The browser suite cannot run against a remote URL (it needs bench access to the site's
    container and `developer_mode`); staging currently gets only `smoke.sh` + the healthcheck. Either build a staging-safe e2e mode or
    accept the gap in writing.
22. [ ] **Decide the missing items the PROGRESS file lists**: pin Python dependencies for the image, the `/v1/login` question,
    branding of outgoing mail, who is on call (`docs/runbooks/incident-response.md` has placeholders).
