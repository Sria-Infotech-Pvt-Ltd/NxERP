# helpdesk-local-dev

Upstream Helpdesk's stand-alone quick start (`docker-compose.yml` + `init.sh`): a Frappe 15 bench with **stock Helpdesk
only**, for trying Helpdesk on its own. It is **not** the NXERP stack (Frappe 16, ERPNext, the platform app): that is
`deploy/bootstrap/up.sh`. It was `frappe-helpdesk-docker/` in the old workspace.

It contains upstream's public demo defaults (database and Administrator passwords for a throw-away local site). Never
reuse them anywhere else. A near-identical pair also ships in `apps/helpdesk/hd-docker/`.
