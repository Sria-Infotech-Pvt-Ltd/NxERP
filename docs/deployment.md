# Deployment Status and Requirements

## Current status

The public URL `https://nxerp.nxsys.in/` is treated as production. Its server architecture, staging counterpart, CI credentials, repository checkout paths, and release process have not been verified. No deployment workflow is active. The `cd-staging.yml` file is a manual status notice and performs no deployment.

This project is not deployment-ready until an isolated staging site is available and the steps below have been confirmed there. Do not use this guide to make changes to production.

## Prerequisites for staging automation

The platform and operations owners must establish and document:

- The staging URL, Frappe site name, Bench version, app repository remotes and refs, and app paths.
- The supported Python, Node, database, Redis, and operating-system versions.
- A non-production deployment identity with least-privilege access and host-key verification.
- A serialized deploy mechanism and GitHub environment approval rules.
- A verified database and files backup, migration procedure, health check, and tested rollback.
- CI passing against the exact commit being deployed.

After these are confirmed, implement a staging-only workflow using GitHub Environment secrets, pinned actions, strict host-key checking, immutable commit SHAs, a backup gate, migration/build steps, and a post-deployment health check. Do not use `git reset --hard` against mutable branch refs.

## Production

Production deployment remains a manual operations action. Before any change, follow the organization's approved change window, backup, review, migration, verification, and rollback procedures. Never infer those commands or service paths from this repository. A GitHub release or push does not deploy the production site.

## Release workflow

`release.yml` creates a GitHub Release from a version tag. It does not deploy code. Release permissions and tag protection still require verification against GitHub repository settings.
