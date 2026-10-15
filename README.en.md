# OpenVMA

[中文](README.md) · [Getting started](docs/getting-started.md) · [Architecture](docs/architecture.md)

The repository is now [VideoX](https://github.com/WowCoder/VideoX); the application retains the OpenVMA name.

OpenVMA is a desktop-browser video workspace for real media assets, scripts, storyboards, material selection, a project's main timeline, and FFmpeg export. It includes a React/TypeScript frontend, FastAPI backend, Celery workers, PostgreSQL/pgvector, Redis, MinIO, and optional local AI services.

AI is optional. Models produce structured drafts, search plans, matching candidates, and generated media. Users select material; backend code validates revisions, schedules jobs, compiles the composition, and renders it.

![Actual OpenVMA project workspace](docs/assets/workspace-smoke.jpg)

Actual workspace: a three-second original test clip, manual storyboard, and offline export with AI services disabled. See [verification scope](docs/open-source-readiness.md).

Available workflows include:

- Upload and process video/audio, create thumbnails and shot segments, edit scenes and shots, mix audio, and export MP4.
- Retrieve semantic candidates with Embedding and optional reranking; matching does not automatically select a candidate.
- Discover topics from fetched sources and monitor source changes with deterministic diffs and validated citations.
- Generate storyboard images/video with explicit DashScope or Agnes configuration; sketch effects and TTS currently use DashScope only.
- Persist video submission, polling, and media transfer separately, with queue and in-flight limits and protection against duplicate paid submissions.

Each project has one script and main composition. Revision checks protect edits; stale generated results are retained as media versions rather than replacing a newer selection. Multiplayer collaboration is not available. See [limitations](docs/limitations.md).

## Start without AI credentials

Install Docker Engine/Desktop and Compose v2, then:

```bash
git clone https://github.com/WowCoder/VideoX.git
cd VideoX
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
```

The example disables all AI providers, so this baseline neither downloads models nor invokes paid AI. Check existing environment files before starting. Visit [localhost:5273](http://localhost:5273), register with email, create a blank project, upload your own short video, add scenes/shots, select media, compile the main composition, and export MP4.

API documentation is at [localhost:8000/docs](http://localhost:8000/docs). Check jobs with `docker compose logs -f backend celery-worker celery-beat`. For admin development, use `npm run dev:admin` in `frontend/`, at [localhost:5274/admin.html](http://localhost:5274/admin.html), with a separate administrator account and TOTP. The regular Vite dev server also serves `/admin.html`; production separation uses distinct builds and gateway configuration.

For local AI, explicitly set the four core providers to `local` in `.env` before running `docker compose --profile local-ai up -d --build`. Cloud capabilities require their explicit provider setting, credentials, enabled models, and a service account that may incur charges. There is no silent local-to-paid fallback. See [configuration](docs/configuration.md).

The root Compose file is a development environment. Use the [production deployment guide](deploy/README.md) for protected gateways, immutable images, backups, migrations, and rollback.

## Development and showcase

Node 22 and Python 3.12 are used for host development. `make check` runs checks through the running development containers. See [development](docs/development.md) for host workers, migrations, and separate app/admin builds.

The Pages showcase reuses the existing homepage design through an independent build, with no application API or account dependency:

```bash
cd frontend
npm ci
npm run build:pages
```

Output: `frontend/dist-pages/`; default base: `/VideoX/`. Deployment requires a public repository and an explicit `PAGES_ENABLED=true` repository variable; the migration remains private until maintainer approval. `https://WowCoder.github.io/VideoX/` is the expected URL after deployment. See the [Pages setup guide](docs/github-pages.md).

Code is licensed under [MIT](LICENSE). Third-party assets, model weights, and hosted services have their own terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md). Security reporting: [SECURITY.md](SECURITY.md).
