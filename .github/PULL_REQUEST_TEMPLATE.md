## What and why

<!-- One paragraph. Link the issue. -->

## Scope check

- [ ] Touches only the area I own, or I have asked the owners of the other area (see CODEOWNERS)
- [ ] No app imports another app (the platform resolves apps; apps do not depend on each other)
- [ ] No secrets, customer data or personal data (use `user@example.test`-style fake data)
- [ ] Any new patch is idempotent and listed in `patches.txt`; any pin change updates `deploy/` and the matching ADR
- [ ] Access change? Enforced on the server (URLs and APIs), not only hidden in the UI

## Evidence

<!-- Paste what you ran and saw: test output, curl status codes, screenshots. "Should work" is not evidence. -->

## Rollback

<!-- How to undo this if it misbehaves in an environment. -->
