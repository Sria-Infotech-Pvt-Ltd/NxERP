# handoff

The old workspace kept git bundles here. They are **not** in the repository (one is 62.7 MB, over the 50 MB limit) and
are archived outside it (`_archive/bundles/` next to the repository folder):

| Bundle | Contents | Status |
| --- | --- | --- |
| `helpdesk-fork.bundle` | Helpdesk branches `feature/nxerp-platform-login` (`3897718`), `phase-4/helpdesk-parity` (`8f77254`) | Both heads are on the company fork remote: redundant |
| `nxerp-platform.bundle` | platform branches `phase-1..4` and tag `v0.1.0-pre.1` | Older snapshot of the same work (28 commits on phase-4 against 39 on the remote); the tag exists only here |
| `nxerp-phase-2-access-layer.bundle` | `phase-2/access-layer` (`1d90f11`) | Older snapshot |

To read one: `git clone <bundle> temp-folder`. Do not commit bundles.
