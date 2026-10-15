# Original Repository Open Source Preparation Implementation Plan

> Historical preparation plan for the original repository. The subsequent independent private-repository migration is recorded in [the VideoX migration plan](2026-10-15-videox-migration.md).

> **For agentic workers:** Use superpowers:subagent-driven-development for the independent tasks below. The user approved the implementation scope in this chat on 2026-10-10; no second approval of that scope is needed.

**Goal:** Prepare a truthful, usable and sanitized MIT-licensed project for public review, with a standalone GitHub Pages showcase.

**Architecture:** Keep the FastAPI/Celery application and production deployment intact. Repair local onboarding, document the actual bounded AI workflows, and build a separate static React showcase using the existing branding and style. Prepare sanitized Git history locally before any remote replacement or publication.

**Tech Stack:** React 19, TypeScript, Vite, Node 22, FastAPI, Celery, PostgreSQL/pgvector, Redis, MinIO, FFmpeg, GitHub Actions.

**Spec:** The reviewed findings and six-step implementation plan in this chat, explicitly approved by the user. User subsequently selected MIT and retaining the repository with sanitized history.

## Global Constraints

- Do not reproduce any private account identifiers or credential values in documentation, output or test fixtures.
- Work on `codex/open-source-preparation`; the managed worktree was unwritable, so use the clean original checkout on this branch.
- No production deploy, paid AI calls, remote force push, repository visibility change or fabricated demonstration/benchmark.
- MIT copyright holder: WowCoder; verify third-party assets separately and retain required attribution.
- Shared files have one owner. Implementers must not stage, commit, rewrite history or edit files owned by another task.
- Meaningful behavior tests precede behavior fixes. Human prose and simple configuration get direct validation rather than source-text tests.

## Review Focus

- Email login and registration preserve the pending creation action; invalid inputs and server errors remain visible.
- Container API/WebSocket proxy targets backend, while host development keeps localhost; no secret enters the static build.
- Root environment loading remains deterministic for host and Docker usage; production credential validation stays strict.
- Pages works under the original repository project path, has no account/API dependency, no paid membership UI, and uses only redistributable assets.
- Sanitization excludes account data across publishable history; private recovery material stays outside the repository and remote remains unchanged.

## Task 1: Local onboarding

**Files:** `frontend/src/views/AuthPage.tsx`, necessary auth styles/helpers/tests, `frontend/vite.config.ts`, `docker-compose.yml`, `backend/app/config.py`, corresponding backend tests.

**Interfaces:** Public AuthPage calls the existing authStore email login/register actions and keeps postAuthAction. `VITE_API_PROXY_TARGET` is server-only configuration for host/Compose; no runtime API hostname is baked into the browser. Settings reads repository `.env` for host usage and environment variables for Docker.

- [ ] Reproduce the proxy/env/login failures and add tests for the relevant request/configuration boundaries.
- [ ] Add accessible email login/register controls, with existing schema rules and real API calls; retain phone/WeChat.
- [ ] Configure Compose frontend proxy to `http://backend:8000` and keep host default `http://localhost:8000`.
- [ ] Make environment-file resolution independent of cwd and remove organization-specific SMS defaults; update affected tests.
- [ ] Run backend unit tests, frontend tests, lint and production/admin builds; report exact commands and results.

## Task 2: Static project showcase

**Files:** `frontend/pages/index.html`, `frontend/src/pagesMain.tsx`, `frontend/src/pages/*`, `frontend/vite.pages.config.ts`, `frontend/package.json`, `.github/workflows/pages.yml`; shared brand paths only where necessary.

**Interfaces:** `npm run build:pages` emits `frontend/dist-pages/index.html`; base uses the original repository project path. Source/docs links target the legacy private repository. Showcase avoids App, auth stores and API clients.

- [ ] Build a standalone project landing page using existing styling/branding and evidence-backed capabilities.
- [ ] Use local first-party visuals; exclude images lacking verified reuse permission from Pages artifacts.
- [ ] Provide source, quickstart and architecture links; no login/payment forms or unavailable live demo link.
- [ ] Add a manual/main-branch Pages workflow with isolated permissions and build-artifact deployment.
- [ ] Verify production build under the project path, all local resources, no API calls, accessible navigation and responsive layout.

## Task 3: README and technical documentation

**Files:** `README.md`, `README.en.md`, `docs/getting-started.md`, `docs/architecture.md`, `docs/configuration.md`, `docs/development.md`, `docs/github-pages.md`, `docs/limitations.md`, relevant existing deployment prose.

**Interfaces:** README links to the exact `build:pages` command, proxy variable and email workflow produced above. Architecture explains actual search planning, citation validation, candidate review, persistent generation and deterministic compilation.

- [ ] Rewrite Chinese README to roughly 150–220 lines with accurate capabilities, architecture, source evidence and safe quickstart.
- [ ] Add concise English README and move operational/provider details into coherent technical docs.
- [ ] Correct removed collaboration/snapshot claims, current providers/TTS, host `.env`, worker queues and separate admin startup.
- [ ] Mark paid/vendor/local-model prerequisites and current limitations without fabricated metrics or preview screenshots.
- [ ] Check every local doc link and every documented command against final code.

## Task 4: Sanitization, governance and CI

**Files:** remove private one-off account migration script, `.gitignore`, `.env.example`, `.env.production.example`, `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `THIRD_PARTY_NOTICES.md`, `.github/ISSUE_TEMPLATE/*`, `.github/pull_request_template.md`, `.github/workflows/check.yml`, secret/dependency checks.

- [ ] Remove tracked account mappings; generalize example domains and SMS identity values.
- [ ] Ignore environment variants and private key/backup material while preserving public example templates.
- [ ] Add MIT, contribution/security guidance and structured issue templates without invented contact details.
- [ ] Add frontend tests to CI and automated secret/dependency checks; record external assets with their confirmed or unresolved status.
- [ ] Scan current publishable files and validate Compose examples and workflow structure.

## Task 5: Verification and history preparation

- [ ] Run backend/frontend suites, lint, app/admin/Pages builds and Compose validation in the completed branch.
- [ ] Perform browser checks of email auth and Pages; attempt a separate clean local stack and media-export flow if Docker access/resources permit, without touching existing data.
- [ ] Request independent code/spec review and resolve material findings.
- [ ] Create private recovery material outside the repository and sanitize all publishable history in a temporary mirror using git-filter-repo.
- [ ] Prove account mappings/operational identity values are absent from sanitized refs; preserve and verify current tree and remote identity.
- [ ] Deliver reviewable changes, verified scope and remaining remote publication steps. No remote rewrite/publication until the prepared result has been reviewed.
