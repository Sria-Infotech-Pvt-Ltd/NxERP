## Summary

<!-- One or two sentences describing what this PR does and why. -->

Closes <!-- NX-XXXX or issue link -->

---

## Type of Change

<!-- Check all that apply -->

- [ ] `feat` — New feature
- [ ] `fix` — Bug fix
- [ ] `refactor` — Code restructure without behaviour change
- [ ] `perf` — Performance improvement
- [ ] `docs` — Documentation only
- [ ] `style` — Formatting, linting
- [ ] `test` — Test additions or fixes
- [ ] `ci` — CI/CD workflow change
- [ ] `chore` — Dependency update, config change

---

## Changes

<!-- List the key files changed and what was done. Be concise but complete. -->

-
-

---

## Test Plan

<!-- How was this change tested? What scenarios were verified? -->

- [ ] Unit tests added / updated (run `bench run-tests --app helpdesk`)
- [ ] Manually tested on local bench
- [ ] Tested with real ERPNext integration
- [ ] Tested on staging (link: )

---

## Self-Review Checklist

- [ ] The code follows the project's style guidelines (no lint errors)
- [ ] All new API methods have `@frappe.whitelist()` and permission checks
- [ ] No hardcoded credentials, URLs, or environment-specific values
- [ ] No `print()` / `console.log()` left in production paths
- [ ] Database queries use the ORM or parameterized SQL
- [ ] Migrations/patches are idempotent and registered in `patches.txt`
- [ ] Branding/CSS uses design tokens (no hardcoded colours)
- [ ] Documentation updated where relevant

---

## Security Impact

<!-- Does this PR change authentication, sessions, permissions, file uploads, or API exposure? If yes, describe the impact. -->

- [ ] No security impact
- [ ] Yes — described below:

---

## Breaking Changes

<!-- Does this PR break any existing API, DocType field, or behaviour? -->

- [ ] No breaking changes
- [ ] Yes — migration / upgrade steps documented:

---

## Reviewer Notes

<!-- Anything specific reviewers should focus on or areas you're unsure about. -->
