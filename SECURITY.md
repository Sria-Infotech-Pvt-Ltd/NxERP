# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest `main` | ✅ Yes |
| Any release older than 90 days | ⚠️ Best-effort |

---

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities privately:

1. **GitHub Security Advisories (preferred):**  
   Navigate to **Security → Advisories → Report a vulnerability** in this repository.

2. **Email:**  
   Send a GPG-encrypted message to the repository security contact listed in the GitHub organization settings.

### What to Include

- A clear description of the vulnerability
- Steps to reproduce (including environment, versions, and configuration)
- The potential impact and attack scenario
- Any proposed mitigations or patches (optional but appreciated)

### Response Timeline

| Stage | Target |
|-------|--------|
| Acknowledgement | Within 2 business days |
| Initial triage | Within 5 business days |
| Status update | Within 14 business days |
| Resolution | Depends on severity; critical issues prioritized |

---

## Security Standards

### Authentication and Sessions

- All authentication uses Frappe's built-in session management
- No custom password databases or parallel authentication systems
- Login tokens are server-side session cookies (HTTP-only, Secure, SameSite=Lax)
- CSRF protection enforced by Frappe on all state-changing requests
- Two-factor authentication available via Frappe configuration

### API Authorization

- All API methods use `@frappe.whitelist()` with role/permission guards
- Guest-accessible endpoints are explicitly listed in `helpdesk/auth.py`
- `frappe.only_for()` is used for role-specific endpoints
- Permission query conditions enforce row-level access on all public DocTypes

### Database

- All database queries use Frappe's ORM or parameterized `frappe.db.sql()` — never string formatting
- No raw SQL in migrations; all schema changes use Frappe DocType definitions or safe patch scripts
- Production database access is restricted to the bench service account

### Secrets

- No secrets, credentials, API keys, or private keys are committed to this repository
- Production secrets are managed via environment variables and Frappe's `site_config.json` (excluded from version control)
- GitHub Actions secrets are scoped to the minimum required workflow
- CI never prints secret values in logs

### Dependencies

- Python dependencies are pinned in `pyproject.toml`
- Node dependencies are pinned in `yarn.lock`
- Dependency audits run automatically on every PR (see `.github/workflows/security.yml`)
- Critical CVEs block PR merging; high CVEs require a documented exception

### File Uploads

- File uploads are processed by Frappe's built-in file handler
- Allowed MIME types and size limits are configured in site settings
- Uploaded files are stored outside the web root (no direct URL execution)

### Logging

- Application logs never contain passwords, session tokens, or personal data
- Error messages shown to users do not include stack traces or internal paths in production

---

## Known Security Limitations

- The NXERP login page extends the Frappe framework login template. Any vulnerability in the Frappe login flow affects this application. Monitor [Frappe security advisories](https://github.com/frappe/frappe/security/advisories).
- The Helpdesk app uses `auth_hooks` to restrict non-system-user access to certain API paths. This is a defence-in-depth measure, not a replacement for Frappe's core permission checks.

---

## Security Tooling

The following checks run automatically on every pull request:

| Tool | What it checks |
|------|---------------|
| `gitleaks` / `trufflehog` | Secret detection in diffs and commit history |
| `pip-audit` | Python dependency CVEs |
| `yarn audit` | Node dependency CVEs |
| `semgrep` (Frappe rules) | Frappe-specific anti-patterns, SQL injection, XSS |
| `ruff` | Python static analysis and style |

---

## Credential Rotation

If a secret is discovered in commit history or logs:

1. Treat the credential as **compromised immediately**
2. Rotate it before any other action
3. Use `git filter-repo` or BFG Cleaner to purge it from history (coordinate with repository administrators)
4. Force-push the cleaned history only after all collaborators are informed
5. Report to the security team

**Do not** use `git commit --amend` or `git rebase` alone — these do not remove the secret from GitHub's cache.
