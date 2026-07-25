# Development

This guide covers local setup, the per-area development loops, code generation, and the environment-variable groups. It documents the current implemented state. Commands run through `just`; run `just --list` for the full recipe set.

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| uv | Python package and venv manager (backend, worker, mcp, contract) | https://docs.astral.sh/uv/ |
| just | Command runner for all recipes | https://github.com/casey/just |
| Node.js | Frontend and E2E toolchain (version 22) | https://nodejs.org/ |
| Docker | Postgres, Redis, the full stack, and E2E | https://docs.docker.com/get-docker/ |

## Environment setup

Copy the annotated example file to a working `.env`:

```sh
cp .env.example .env
```

`.env.example` is the canonical, sectioned list of the dev/local variables, grouped by consumer. Read it for the meaning and default of each key. `floresu.core.settings` anchors the file to the repo root, so a host inner-loop recipe loads it regardless of the recipe working directory. Compose and CD inject real environment variables, which always win over the file.

## Development workflows

### Python packages

Each Python package (`backend`, `worker`, `mcp`, and the dev-only `contract`) is an independent uv project with its own lockfile and virtualenv, so it can build into its own image. `just install` runs `uv sync` in each package and `npm install` in the frontend. Work inside a package with `uv run`:

```sh
cd backend && uv run pytest      # run one package's suite
cd mcp && uv run ruff check .    # lint one package
```

### Local data services

```sh
just up          # start local Postgres (pgvector) + Redis, host-published
just down        # stop the local dev services
just migrate     # apply migrations up to head against DATABASE_URL
```

`just up` layers `docker-compose.dev.yml` on the base file so Postgres and Redis publish to localhost for the host inner loop. It also populates the Prometheus config env vars from the committed files so the base compose file parses.

### Backend host inner loop

```sh
just dev-api             # external app on http://127.0.0.1:8000, autoreload
just dev-api-internal    # internal app on http://127.0.0.1:8001, autoreload
just serve-backend       # run both apps together, as the container does
```

Run the two apps in separate terminals for the split inner loop, or `just serve-backend` to run both. The external app serves the SPA and the OAuth AS; the internal app serves the routes the MCP server and the embed worker call.

### Frontend

```sh
cd frontend && npm run dev        # SPA against the real backend
cd frontend && npm run dev:mock   # SPA against the MSW mock harness (VITE_MOCK_API=true)
```

Use `npm run dev:mock` to develop the SPA with no backend running. It serves the REST responses from the MSW handlers in `frontend/src/mocks/`.

### MCP server and worker

The MCP server and the embed worker run against the internal app. Start them from their package with `uv run`, or bring up the whole stack:

```sh
just up-dev      # full stack in Docker: built images, dev env, host-published data
```

The MCP RS validates agent tokens against the external app's JWKS, so run the external app (or the full stack) alongside it.

### End-to-end

```sh
cd e2e && npm run infra:up     # bring up the E2E infra (Postgres, Redis, MinIO)
cd e2e && npm test             # bring up infra, then run the Playwright suite
cd e2e && npm run infra:down   # tear down the E2E infra
```

Playwright starts the app processes (both ASGI apps, the frontend production build, and a fake embedding provider). No run calls OpenAI or real R2. See `docs/testing.md` for the layers and `docs/ci-cd.md` for how CI runs E2E.

## Code generation

The frontend REST client is generated, never hand-written.

```sh
just codegen           # export the external OpenAPI document, then run openapi-typescript
```

`just codegen` writes `frontend/openapi.json` from the external app, then regenerates `frontend/src/api/schema.d.ts` (consumed by `client.ts`). Run it after any change to the external REST surface. CI drift-gates it: the `codegen-drift` job fails on a stale committed client.

The MCP wire schemas are not generated. They are hand-authored in `mcp/src/floresu_mcp/schemas_*.py` and kept in sync with the backend by the `contract/` drift tests, not by codegen.

## Resume schema goldens

The resume document shape is locked by a golden snapshot plus an append-only hash lock.

```sh
just resume-goldens    # regenerate the current golden and append its sha256
```

Run `just resume-goldens` only after bumping the current schema version and registering an upcaster. It refuses to overwrite a released golden, so a locked shape stays frozen. The `resume-schema-lock` CI job fails until the new golden is committed. See `docs/ci-cd.md`.

## Environment variables

`.env.example` is the canonical annotated list of the dev/local variables. The production, non-secret half is committed in `.env.prod`. The backend and internal apps read their variables through `core/settings.py`; the MCP server and the worker read theirs through their own settings modules (`mcp/src/floresu_mcp/settings.py`, `worker/src/floresu_worker/settings.py`). The variables group by consumer:

| Group | Keys | Purpose |
|-------|------|---------|
| Core | `ENVIRONMENT`, `LOG_LEVEL`, `HOST` | Runtime identity; `development` renders console logs, anything else renders JSON |
| Database | `DATABASE_URL` | The async SQLAlchemy connection URL (asyncpg driver) |
| Redis | `REDIS_URL` | The arq queue, the SSE feed pub/sub, and the rate-limit counters |
| Internal trust boundary | `INTERNAL_API_TOKEN`, `BACKEND_INTERNAL_URL` | The shared secret and the internal URL the MCP server and worker call |
| Human sessions and CORS | `SESSION_JWT_SECRET`, `COOKIE_DOMAIN`, `CORS_ORIGIN` | The HS256 session secret, the cookie apex, the SPA origin allowed to send credentialed XHRs |
| Pinned public URLs | `PUBLIC_BASE_URL`, `APP_PUBLIC_URL`, `MCP_PUBLIC_URL` | The AS origin/token `iss`, the consent SPA, the MCP resource the agent token is audience-bound to |
| OAuth 2.1 AS | `OAUTH_PRIVATE_KEY_PATH`, `OAUTH_KEY_ID`, `OAUTH_ACCESS_TTL_SECONDS`, `OAUTH_REFRESH_TTL_SECONDS`, and the reaper knobs | The signing key, active `kid`, token TTLs, and the stale-client reaper |
| MCP resource server | `MCP_TRUSTED_PROXIES`, `RATE_LIMIT_WINDOW_SECONDS`, `RATE_LIMIT_REQUEST_BUDGET`, `RATE_LIMIT_EMBED_WRITE_BUDGET` | The trusted proxy CIDR and the per-user rate-limit budgets |
| Embedding provider | `OPENAI_API_KEY`, `OPENAI_BASE_URL` | The only external AI dependency; an empty key lets a box boot and items stay lexically searchable |
| Object storage (R2) | `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | S3-compatible storage for rendered PDFs |
| Worker | `WORKER_METRICS_PORT` | The port the worker exposes its metrics on |

The embedding model and vector dimension are pinned in `floresu.embedding.config` (changing them is a migration), so they are not tunable settings.

### OAuth stale-client reaper knobs

The external app runs a background reaper that reaps stale open-registration OAuth clients:

| Variable | Default | Meaning |
|----------|---------|---------|
| `OAUTH_CLIENT_CLEANUP_INTERVAL_SECONDS` | `21600` (6 hours) | How often the sweep runs. A non-positive value disables the task. |
| `OAUTH_STALE_CLIENT_MAX_AGE_SECONDS` | `2592000` (30 days) | The registration-age threshold for a reap. Independent of the refresh-token TTL. |

See `docs/auth.md` for the reaper and `backend/src/floresu/oauth/` for the implementation.

## Cross-references

- Testing layers and commands: `docs/testing.md`.
- CI jobs and the deploy pipeline: `docs/ci-cd.md`.
- The generated client and the REST surface: `docs/api.md`.
- System topology and trust zones: `docs/architecture.md`.
