# VideoX Private Repository Migration Plan

> **For agentic workers:** Use superpowers:executing-plans to complete the authorized migration and verify each external action.

**Goal:** Create an independent private `WowCoder/VideoX` repository and migrate the sanitized project while leaving publication for the maintainer's later confirmation.

**Architecture:** Preserve the cleaned main-branch ancestry. Create a new empty repository rather than a fork or repository transfer. Update current repository links and the Pages project path; retain existing application identifiers and image assets. Push only the prepared main branch.

**Tech Stack:** Git, GitHub, React/Vite, GitHub Actions.

**Spec:** The maintainer requested a new private repository named `VideoX`, migration, and no public release before confirmation.

## Global Constraints

- New repository owner/name: `WowCoder/VideoX`; visibility: **Private**.
- Original `WowCoder/OpenVMA` stays private and is not overwritten or deleted.
- Do not migrate old server caches, workflow logs, unreviewed refs, secrets, local environment files, media, or recovery backups.
- Keep sanitized commit authorship and MIT/third-party notices.
- Do not publish Pages during migration. Require public visibility and an explicit `PAGES_ENABLED=true` repository variable before its workflow can deploy.
- Preserve the original remote under `openvma` when making VideoX the local `origin`.

## Review Focus

- A repository with the requested name already exists: inspect it, do not overwrite it.
- Current documentation still sends users to the old repository or clone directory.
- Pages assets break under the new case-sensitive `/VideoX/` prefix.
- Old-repository cache cleanup is incorrectly treated as a release dependency for the independent new repository.
- A migration push accidentally includes original refs or triggers publication.

## Tasks

- [x] Create and verify an empty independent private `WowCoder/VideoX` repository.
- [x] Update clone instructions, contribution/security links, static homepage repository links and the Pages base path.
- [x] Gate Pages deployment on public visibility and explicit enablement; document the release procedure.
- [x] Distinguish old-repository cleanup evidence from the new repository's migration and publication gates.
- [ ] Run frontend checks/builds, local Markdown link validation and Gitleaks over the prepared history.
- [x] Independently review the migration diff and resolve material findings.
- [ ] Commit with the maintainer's GitHub noreply email, then push only `HEAD:main` to the verified private repository.
- [ ] Verify remote SHA, clean-history ancestry, exact migrated tree, Private visibility, and Check/Security results.
- [ ] Make VideoX the local origin, retain the original private remote, and report the repository URL and remaining publication decision.
