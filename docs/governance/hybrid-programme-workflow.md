# Git workflow for the hybrid database programme (Phase 0 decision)

Applies to the eight phases of the NXDESK hybrid database blueprint. Normal feature work still follows [CONTRIBUTING.md](../../CONTRIBUTING.md).
Everything here is a **DECISION** made in Phase 0 to resolve contradictions in the blueprint; the contradictions and corrections are listed at the end.

## Folders (siblings, never nested)

```
C:\PROJECTS DEV\NXDESK CORE\
  NXERP SRIA CORE\   original checkout. Owns the real .git. Stays on feat/nxdesk-onboarding. Holds the owner's uncommitted work. Do not run phases here.
  NXDESK-track-A\    Git worktree for Track A: Phases 1, 5, 6, 8
  NXDESK-track-B\    Git worktree for Track B: Phases 2, 3, 4, 7
```

A worktree is another checkout of the **same repository** (one history, one object store). It is not a copy of the code and not a separate repository.
Code changes happen in whichever worktree has the branch checked out. Changes move between tracks only through Git branches (merge or pull request), never by copying files.
A branch can be checked out in only one worktree at a time.

## Branches

One **base**, then one **stacked branch per phase**. There are no `hybrid/track-a` or `hybrid/track-b` branches: a worktree switches to the current phase branch instead.

| Branch | Created from | Worktree | Phase |
| --- | --- | --- | --- |
| `hybrid/phase-0-foundation` | `feat/nxdesk-onboarding` (`8a4910610`) | (none after Phase 0) | the base: identity docs, ecosystem registry, this workflow |
| `hybrid/phase-1-harden` | `hybrid/phase-0-foundation` | Track A | 1 |
| `hybrid/phase-2-contracts` | `hybrid/phase-1-harden` once work package 1C is committed | Track B | 2 |
| `hybrid/phase-3-outbox` | `hybrid/phase-2-contracts` | Track B | 3 |
| `hybrid/phase-4-shared-layer` | `hybrid/phase-3-outbox` | Track B | 4 |
| `hybrid/phase-5-stacks` | `hybrid/phase-1-harden` | Track A | 5 |
| `hybrid/phase-6-identity` | `hybrid/phase-5-stacks` | Track A | 6 |
| `hybrid/phase-7-reads-writes` | `hybrid/phase-4-shared-layer`, then merge `hybrid/phase-6-identity` | Track B | 7 |
| `hybrid/phase-8-cutover` | `hybrid/phase-6-identity`, then merge `hybrid/phase-7-reads-writes` | Track A | 8 |

`hybrid/phase-8-cutover` ends up containing every phase. It is the integration branch; one reviewed pull request from it goes back to `feat/nxdesk-onboarding`
(and from there along the normal route to `develop` and `main`).

## Rules

1. **Start a phase:** in the track's worktree, `git switch -c <phase branch> <parent>`. The previous phase branch stays as it is.
2. **Pull requests:** one draft PR per phase, with the branch it was created from as base. Needs the base to exist on origin, so the base chain is pushed first. **Nothing is pushed without the owner's approval.**
3. **Merge commits, never squash,** for every hybrid PR. Phases are stacked, and squashing a parent rewrites commits its children are built on.
4. **Cross-track merges** happen only in Phase 7 (merges Phase 6) and Phase 8 (merges Phase 7). Claude Code resolves conflicts there; `docs/PROGRESS.md` conflicts are resolved by keeping both entries.
5. **ADR-009** is created in Phase 1 (work package 1C, status Proposed). Phase 2 **edits** it; it must not create it again.
6. If a parent branch gains commits after a child was created, merge the parent into the child (`git merge <parent>`); never rebase a branch that has been pushed or reviewed.
7. The original folder is protected: never reset, clean, stash or check out over its uncommitted files. Never push `main` or `develop`, never force-push.

## Contradictions in the blueprint and the correction applied

| # | Blueprint says | Problem | Correction |
| --- | --- | --- | --- |
| 1 | Setup 0.7: worktrees on `hybrid/track-a` and `hybrid/track-b`. Each phase prompt: new phase branch inside that worktree | A worktree holds one branch, so the track branches would never be used | No track branches; the worktree switches to the phase branch |
| 2 | Base is `feat/nxdesk-app-login` | The branch does not exist locally or on origin | Base is `feat/nxdesk-onboarding`, via `hybrid/phase-0-foundation` |
| 3 | PR base is the branch the phase was created from | The base was never pushed | Push the base chain first, with owner approval |
| 4 | "Merge the pull request (squash is fine)" | Squash breaks stacked branches | Merge commits only |
| 5 | Phase 1 (1C) and Phase 2 (2B) both create `ADR-009-hybrid-database-architecture.md` and its index row | Add/add conflict when the chains meet | Phase 1 creates it; Phase 2 edits it |
| 6 | Dependency table: Phase 2 needs Phase 1. Timeline: they run in parallel. Phase 2 prompt: "Preconditions: None", from the base | Contradictory; also causes 5 | Phase 2 starts from `hybrid/phase-1-harden` after 1C is committed |
